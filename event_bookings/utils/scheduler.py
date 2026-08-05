import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, now_datetime, today


def daily():
	"""Daily scheduled tasks."""
	for task_name, task in (
		("sync_invoice_payment_status", sync_invoice_payment_status),
		("send_unstaffed_alerts", send_unstaffed_alerts),
		("notify_managers_upcoming_events", notify_managers_upcoming_events),
	):
		try:
			task()
		except (frappe.DatabaseError, frappe.ValidationError):
			frappe.log_error(title=f"Event Bookings daily task failed: {task_name}")


def sync_invoice_payment_status():
	"""Transition Invoiced → Paid when linked Sales Invoice is paid."""
	from event_bookings.utils.erpnext_bridge import is_erpnext_installed
	if not is_erpnext_installed():
		return

	events = frappe.get_all(
		"Event Booking",
		filters={"booking_status": "Invoiced", "sales_invoice": ("is", "set"), "docstatus": 1},
		fields=["name", "sales_invoice"],
		limit_page_length=0,
	)
	if not events:
		return

	sales_invoices = list({eb.sales_invoice for eb in events})
	si_statuses = frappe._dict(
		frappe.get_all("Sales Invoice", filters={"name": ("in", sales_invoices)}, fields=["name", "status"], as_list=1, limit_page_length=0)
	)

	for eb in events:
		try:
			if si_statuses.get(eb.sales_invoice) != "Paid":
				continue
			# Re-read current state before writing — the list was fetched earlier
			# and another process may have already updated or cancelled the booking.
			current = frappe.db.get_value(
				"Event Booking", eb.name, ["booking_status", "docstatus"], as_dict=True
			)
			if current and current.booking_status == "Invoiced" and current.docstatus == 1:
				frappe.db.set_value("Event Booking", eb.name, "booking_status", "Paid")
		except (frappe.DatabaseError, frappe.ValidationError):
			frappe.log_error(title=f"Failed to sync payment status for {eb.name}")


def _get_manager_emails():
	"""Return list of email addresses for enabled users with Event Manager role.

	Uses batch fetching to avoid the N+1 anti-pattern.
	"""
	managers = frappe.get_all(
		"Has Role", filters={"role": "Event Manager", "parenttype": "User"}, pluck="parent", limit_page_length=0
	)
	if not managers:
		return []
	return [
		row.email
		for row in frappe.get_all(
			"User",
			filters={"name": ("in", managers), "enabled": 1, "email": ("is", "set")},
			fields=["email"],
			distinct=True,
			limit_page_length=0,
		)
	]


def send_unstaffed_alerts():
	"""Alert Event Managers with a single digest email listing all staffing shortfalls.

	Previous design sent one email per understaffed row, causing email storms on busy
	sites.  All shortfalls are now grouped by booking and delivered as one digest.
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
		WHERE eb.booking_status = 'In Preparation'
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
		if row.name not in events:
			events[row.name] = {
				"event_name": row.event_name,
				"event_date": row.event_date,
				"shortfalls": [],
			}
		events[row.name]["shortfalls"].append(
			_("<li>{0} – required {1}, assigned {2}</li>").format(
				row.designation, int(row.qty_required), int(row.qty_assigned)
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
		_enqueue_email(
			recipients=_manager_emails,
			subject=_("Staffing Alert: {0} event(s) with shortfalls").format(len(events)),
			message="".join(lines),
			reference_doctype="Event Booking",
			reference_name=next(iter(events)),
		)
	except (frappe.DatabaseError, frappe.ValidationError):
		frappe.log_error(title=_("Staffing digest alert failed"))


def notify_managers_upcoming_events():
	"""Send desk notifications to Event Managers for every upcoming event within the next 7 days.

	Collects all required notifications and hands them off to a background enqueue,
	eliminating document inserts inside a nested loop.
	"""
	from_date = today()
	to_date = add_days(today(), 7)
	events = frappe.get_all(
		"Event Booking",
		filters={
			"event_date": ("between", [from_date, to_date]),
			"booking_status": ("in", ["New", "Quoted", "Negotiating", "Confirmed", "In Preparation", "Executed"]),
		},
		fields=["name", "event_name", "event_date", "event_location", "booking_status"],
		limit_page_length=0,
	)
	managers = frappe.get_all("Has Role", filters={"role": "Event Manager", "parenttype": "User"}, pluck="parent", limit_page_length=0)
	if not managers or not events:
		return

	# Use a 24-hour rolling window — calendar-day "since midnight" causes duplicate
	# notifications when the scheduler runs near midnight.
	_dedup_since = add_to_date(now_datetime(), hours=-24)
	existing_logs = frappe.get_all(
		"Notification Log",
		filters={
			"document_type": "Event Booking",
			"document_name": ("in", [e.name for e in events]),
			"type": "Alert",
			"creation": (">=", _dedup_since),
		},
		fields=["for_user", "document_name"],
		limit_page_length=0,
	)
	existing_set = {(log.for_user, log.document_name) for log in existing_logs}

	notifications = []
	for ev in events:
		for manager in managers:
			if (manager, ev.name) in existing_set:
				continue
			notifications.append({
				"subject": _("Upcoming Event: {0}").format(ev.event_name),
				"email_content": _(
					"Event {0} is scheduled for {1} at {2}. Status: {3}"
				).format(
					ev.event_name,
					frappe.utils.formatdate(ev.event_date),
					ev.event_location or "TBD",
					ev.booking_status,
				),
				"for_user": manager,
				"document_type": "Event Booking",
				"document_name": ev.name,
			})

	if notifications:
		frappe.enqueue(
			"event_bookings.utils.scheduler._insert_notification_logs",
			queue="short",
			notifications=notifications,
		)


def _insert_notification_logs(notifications):
	"""Background worker: insert Notification Log documents in batch.

	Uses ``frappe.db.bulk_insert`` (one SQL statement) instead of N individual
	``Document.insert()`` calls to avoid hammering the DB under load.
	Falls back to individual inserts if bulk_insert fails (e.g., schema mismatch).
	"""
	if not notifications:
		return

	now_ts = frappe.utils.now()
	fields = [
		"name", "type", "subject", "email_content",
		"for_user", "document_type", "document_name",
		"creation", "modified", "modified_by", "owner",
		"docstatus", "idx", "read",
	]
	values = [
		[
			frappe.generate_hash("", 10),
			n.get("type", "Alert"),
			n.get("subject", ""),
			n.get("email_content", ""),
			n.get("for_user", ""),
			n.get("document_type", ""),
			n.get("document_name", ""),
			now_ts, now_ts, "Administrator", "Administrator",
			0, 0, 0,
		]
		for n in notifications
	]

	try:
		frappe.db.bulk_insert(
			"Notification Log",
			fields=fields,
			values=values,
			ignore_duplicates=True,
		)
		frappe.db.commit()
	except Exception:
		frappe.logger("event_bookings").warning(
			"Bulk notification log insert failed — retrying individually",
			exc_info=True,
		)
		for n in notifications:
			try:
				frappe.get_doc({
					"doctype": "Notification Log",
					"type": "Alert",
					**n,
				}).insert(ignore_permissions=True)
			except (frappe.DatabaseError, frappe.ValidationError):
				frappe.log_error(title=_("Manager notification failed"))


def _enqueue_email(recipients, subject, message, reference_doctype, reference_name):
	"""Queue an email in the background using the public frappe.sendmail API."""
	frappe.sendmail(
		recipients=recipients,
		subject=subject,
		message=message,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		now=False,
	)
