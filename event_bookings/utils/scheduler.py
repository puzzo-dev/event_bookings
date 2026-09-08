"""Scheduled tasks for Event Bookings.

Only date-based work that has no corresponding document event lives here.
Status automation (Quotation → Quoted, SI submitted → Invoiced, SI paid →
Paid) is event-driven via ``utils/erpnext_hooks.py`` doc_events — exactly
like ERPNext's own Sales Order status flow.

Notifications (pre-event reminders, manager alerts) are handled by Frappe's
built-in Notification service (Email Alert DocType with "Days Before"
scheduling). No custom email-sending code is needed here.

What remains:
- ``auto_execute_passed_events`` — daily: move past Confirmed / In
  Preparation bookings to Executed (no doc event fires when a date passes).
- ``send_unstaffed_alerts`` — daily: digest email to Event Managers for
  staffing shortfalls (grouped query, not a simple per-doc notification).
"""

import frappe
from frappe import _
from frappe.utils import today


def auto_execute_passed_events():
	"""Daily: move Confirmed / Paid bookings to Executed once the event date
	has passed. Gated by the auto_executed_after_event_date setting;
	forward-only per the status order; skips Cancelled and docstatus-2
	bookings. Each change is audited via a timeline comment.

	Also marks linked Sales Orders as Fully Delivered and refreshes Sales
	Invoice status — the event has happened, so the goods/services are
	fulfilled.
	"""
	from event_bookings.utils.status import (
		advance_booking_status,
		cached_settings_toggles,
		settings_toggle_enabled,
	)

	if not settings_toggle_enabled("auto_executed_after_event_date"):
		return

	events = frappe.get_all(
		"Event Booking",
		filters={
			"event_date": ("<", today()),
			"booking_status": ("in", ["Confirmed", "Paid"]),
			"docstatus": ("<", 2),
		},
		fields=["name", "event_name", "sales_order", "sales_invoice"],
		limit_page_length=0,
	)
	# advance_booking_status re-checks enable_automated_status on every call, so
	# without this the batch issues one identical Singles read per booking.
	# Scoped to the loop, so nothing outside this job can read a stale toggle.
	with cached_settings_toggles():
		for eb in events:
			changed = advance_booking_status(
				eb.name,
				"Executed",
				reason="event date has passed (daily scheduler)",
			)
			if changed:
				_mark_linked_documents_delivered(eb)


def _mark_linked_documents_delivered(eb):
	"""When a booking is auto-executed, mark its linked Sales Order as fully
	delivered and update the Sales Invoice status.

	The SO's ``per_delivered`` is set to 100 and ``delivery_status`` to
	"Fully Delivered" via ``db_set`` so we don't trigger ERPNext's full
	validation chain (which would require actual Delivery Notes / Stock
	Entries). The SI status is refreshed via ``set_status`` so it reflects
	the current billing state.

	All writes are exception-safe — a failure on one document never blocks
	the booking's own Executed transition (which already succeeded).
	"""
	from event_bookings.utils.erpnext_bridge import is_erpnext_installed

	if not is_erpnext_installed():
		return

	# Sales Order → Fully Delivered
	if eb.get("sales_order"):
		try:
			so_name = eb["sales_order"]
			so_docstatus = frappe.db.get_value("Sales Order", so_name, "docstatus")
			if so_docstatus == 1:
				frappe.db.set_value(
					"Sales Order", so_name,
					{"per_delivered": 100, "delivery_status": "Fully Delivered"},
					update_modified=False,
				)
				# Single statement instead of a SELECT plus one UPDATE per row:
				# delivered_qty is being set to each row's own qty, which the
				# database can do without the values ever reaching Python.
				frappe.db.sql(
					"""UPDATE `tabSales Order Item`
					   SET delivered_qty = qty
					   WHERE parent = %(so)s""",
					{"so": so_name},
				)
		except Exception:
			frappe.log_error(
				title=_("Failed to mark Sales Order {0} as delivered for booking {1}").format(
					eb.get("sales_order"), eb["name"]
				),
				message=frappe.get_traceback(),
			)

	# Sales Invoice → refresh status (e.g. mark as Paid if fully paid)
	if eb.get("sales_invoice"):
		try:
			si_name = eb["sales_invoice"]
			si_docstatus = frappe.db.get_value("Sales Invoice", si_name, "docstatus")
			if si_docstatus == 1:
				si = frappe.get_doc("Sales Invoice", si_name)
				# `update=True` is the real keyword — `update_status` raised
				# TypeError on every call, and the bare except below swallowed
				# it, so this hook never once advanced a booking.
				# set_status(update=True) writes the column itself, so no
				# follow-up db_set is needed.
				si.set_status(update=True, update_modified=False)
		except Exception:
			frappe.log_error(
				title=_("Failed to refresh Sales Invoice {0} status for booking {1}").format(
					eb.get("sales_invoice"), eb["name"]
				),
				message=frappe.get_traceback(),
			)


def send_unstaffed_alerts():
	"""Alert Event Managers with a single digest email listing all staffing
	shortfalls.

	Grouped by booking and delivered as one digest to avoid email storms.
	"""
	_manager_emails = _get_manager_emails()
	if not _manager_emails:
		return

	rows = frappe.db.sql(
		"""
		SELECT
			eb.name,
			eb.event_name,
			eb.event_date,
			esr.designation,
			esr.qty_required,
			IFNULL(esr.qty_assigned, 0) AS qty_assigned
		FROM `tabEvent Booking` eb
		INNER JOIN `tabEvent Staff Requirement` esr
			ON esr.parent = eb.name AND esr.parenttype = 'Event Booking'
		WHERE eb.booking_status = 'Confirmed'
			AND eb.event_date >= %(today)s
			AND IFNULL(esr.qty_assigned, 0) < esr.qty_required
		ORDER BY eb.event_date ASC
		""",
		{"today": today()},
		as_dict=True,
	)
	if not rows:
		return

	# Group shortfalls by booking so the digest is readable
	events = {}
	for row in rows:
		if row["name"] not in events:
			events[row["name"]] = {
				"event_name": row["event_name"],
				"event_date": row["event_date"],
				"shortfalls": [],
			}
		events[row["name"]]["shortfalls"].append(
			_("<li>{0} – required {1}, assigned {2}</li>").format(
				row["designation"], int(row["qty_required"]), int(row["qty_assigned"])
			)
		)

	# Build a single digest message
	lines = [_("<p>The following upcoming events have staffing shortfalls:</p><ul>")]
	for ev in events.values():
		lines.append(
			"<li><strong>{0} – {1}</strong><ul>{2}</ul></li>".format(
				frappe.utils.formatdate(ev["event_date"]),
				ev["event_name"],
				"".join(ev["shortfalls"]),
			)
		)
	lines.append("</ul>")

	try:
		# No reference_doctype/reference_name: this is a digest covering every
		# short-staffed booking, and `next(iter(events))` attached the whole
		# thing to one arbitrary booking's timeline — the others got nothing,
		# and that one got a Communication listing events it has no part in.
		# A digest belongs to no single document.
		frappe.sendmail(
			recipients=_manager_emails,
			subject=_("Staffing Alert: {0} event(s) with shortfalls").format(len(events)),
			message="".join(lines),
			now=False,
		)
	except Exception:
		# Not `frappe.DatabaseError` — no such name exists on v15 or v16, so a
		# failed digest raised AttributeError out of the scheduled job instead
		# of being logged. A digest that cannot be sent must never take the
		# scheduler down with it.
		frappe.log_error(
			message=frappe.get_traceback(),
			title=_("Staffing digest alert failed"),
		)


def _get_manager_emails():
	"""Return list of email addresses for enabled users with Event Manager role."""
	managers = frappe.get_all(
		"Has Role", filters={"role": "Event Manager", "parenttype": "User"}, pluck="parent", limit_page_length=0
	)
	if not managers:
		return []
	return [
		row["email"]
		for row in frappe.get_all(
			"User",
			filters={"name": ("in", managers), "enabled": 1, "email": ("is", "set")},
			fields=["email"],
			distinct=True,
			limit_page_length=0,
		)
	]
