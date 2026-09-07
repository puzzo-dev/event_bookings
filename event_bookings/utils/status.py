"""Booking status lifecycle helpers.

Status order (user-confirmed):

    New -> Quoted -> Invoiced -> Confirmed -> Paid -> Executed

``Cancelled`` is reachable from any state, but only via the manual cancellation
flow (which also cascades to linked documents) — automation never sets it.

Automation matrix:
- Quotation linked/submitted  → Quoted
- Sales Invoice submitted      → Invoiced
- Sales Invoice partly paid    → Confirmed
- Sales Invoice fully paid     → Paid
- Event date passed            → Executed (daily scheduler)

Design contract
---------------
- ``advance_booking_status`` is **forward-only**: it never moves a booking
  backwards in the order and never touches Cancelled or docstatus-2 bookings.
- It works for both draft (docstatus 0) and submitted (docstatus 1) bookings —
  ``booking_status`` is ``allow_on_submit`` so automation continues after the
  booking is submitted.
- It is **exception-safe**: every failure is logged and returns False so
  callers (ERPNext doc_events on Quotation/Sales Order/Sales Invoice) never
  abort their own save/submit.
- Every automated change leaves a timeline comment so automation is auditable.
"""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import cint

STATUS_ORDER = [
	"New",
	"Quoted",
	"Invoiced",
	"Confirmed",
	"Paid",
	"Executed",
]

CANCELLED = "Cancelled"


def status_index(status):
	"""Return the position of *status* in STATUS_ORDER, or None if unknown/Cancelled."""
	try:
		return STATUS_ORDER.index(status)
	except ValueError:
		return None


def is_forward_transition(current, target):
	"""True when *target* comes strictly after *current* in STATUS_ORDER."""
	current_idx = status_index(current)
	target_idx = status_index(target)
	if current_idx is None or target_idx is None:
		return False
	return target_idx > current_idx


# Memoisation is opt-in, and deliberately not request-wide.
#
# advance_booking_status checks a toggle on every call, so a scheduler batch
# over N bookings issues N identical reads. Caching that globally would be the
# obvious fix and the wrong one: frappe.db.set_single_value writes the Singles
# row directly, bypassing the document layer, so no controller hook can
# invalidate a cache — any request that wrote a toggle and then acted on it
# would read its own stale value.
#
# So the memo only exists inside cached_settings_toggles(), which the scheduler
# wraps around its loop. A batch reads each toggle once; every other caller
# reads live and cannot go stale. Settings changed mid-run are picked up by the
# next run, which is the correct granularity for a daily job.
_TOGGLE_CACHE = "event_bookings_settings_toggles"


@contextmanager
def cached_settings_toggles():
	"""Memoise settings toggle reads for the duration of the block."""
	setattr(frappe.local, _TOGGLE_CACHE, {})
	try:
		yield
	finally:
		if hasattr(frappe.local, _TOGGLE_CACHE):
			delattr(frappe.local, _TOGGLE_CACHE)


def settings_toggle_enabled(fieldname):
	"""Read a Check toggle from Event Booking Settings, defaulting to ON when
	the Singles row is missing.

	Frappe quirk: a Single that has SOME rows saved loads fields without rows
	as 0 (load_from_db skips new_doc defaults; _fix_numeric_types coerces the
	missing value) — and get_single_value/get_cached_doc go through that same
	load path. So a missing row must be read via a direct tabSingles query,
	which returns None only when the row truly does not exist.

	Reads live unless the caller opted into cached_settings_toggles().
	"""
	cache = getattr(frappe.local, _TOGGLE_CACHE, None)
	if cache is not None and fieldname in cache:
		return cache[fieldname]

	value = frappe.db.sql(
		"SELECT `value` FROM `tabSingles` WHERE `doctype` = %s AND `field` = %s",
		("Event Booking Settings", fieldname),
	)
	result = True if not value else cint(value[0][0]) == 1
	if cache is not None:
		cache[fieldname] = result
	return result


def automation_enabled():
	"""Read the enable_automated_status toggle (default ON when unset)."""
	return settings_toggle_enabled("enable_automated_status")


def advance_booking_status(booking_name, target_status, reason=None):
	"""Advance a booking's status to *target_status* if that is a forward move.

	Returns True when the status was changed. Safe no-op (returns False) when:
	- the booking does not exist,
	- the booking is Cancelled or docstatus 2 (cancelled),
	- target is not forward from the current status (never downgrades),
	- automated status is disabled in Event Booking Settings.

	Any error is logged (never raised) so ERPNext document hooks calling this
	cannot break their own transaction.
	"""
	if not booking_name or target_status not in STATUS_ORDER:
		return False

	try:
		current = frappe.db.get_value(
			"Event Booking", booking_name, ["booking_status", "docstatus"], as_dict=True
		)
		if not current:
			return False
		if current.docstatus == 2 or current.booking_status == CANCELLED:
			return False
		if not is_forward_transition(current.booking_status, target_status):
			return False
		if not automation_enabled():
			return False

		update = {"booking_status": target_status}

		# advance_booking_status writes through db.set_value, so the document
		# lifecycle (and EventBooking.stamp_lifecycle_dates) never runs. Stamp
		# confirmed_on here so automated transitions carry the same date basis
		# as manual ones. Written once — never moved by a later transition.
		if status_index(target_status) >= STATUS_ORDER.index("Confirmed") and not frappe.db.get_value(
			"Event Booking", booking_name, "confirmed_on"
		):
			update["confirmed_on"] = frappe.utils.today()

		frappe.db.set_value("Event Booking", booking_name, update)

		_add_timeline_comment(
			booking_name, current.booking_status, target_status, reason
		)
		return True
	except Exception:
		frappe.log_error(
			title=_("Event Bookings: failed to auto-advance status of {0} to {1}").format(
				booking_name, target_status
			),
			message=frappe.get_traceback(),
		)
		return False


def _add_timeline_comment(booking_name, old_status, new_status, reason):
	"""Leave an audit trail on the booking's timeline for an automated change."""
	try:
		text = _("Status auto-advanced from {0} to {1}").format(old_status, new_status)
		if reason:
			text += _(": {0}").format(reason)
		frappe.get_doc("Event Booking", booking_name).add_comment("Comment", text=text)
	except Exception:
		# The status change itself is already persisted — a comment failure
		# must never roll anything back.
		frappe.log_error(
			title=_("Event Bookings: failed to record status-change comment for {0}").format(
				booking_name
			),
			message=frappe.get_traceback(),
		)
