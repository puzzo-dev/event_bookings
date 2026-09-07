"""Backfill ``confirmed_on`` / ``cancelled_on`` on existing Event Bookings.

Both fields are new, so every historical booking has them blank. Analytics that
switch to them would simply drop all history, so reconstruct the dates once:

1. Prefer the Version history — ``tabVersion.data`` records each field change
   with the row's ``creation`` timestamp, which is exactly when the status
   moved. This is the true date.
2. Fall back to ``modified``. That is the (imperfect) basis the charts used
   before these fields existed, so the fallback is never worse than the status
   quo — and unlike ``modified`` it is frozen from here on instead of drifting
   on every unrelated edit.

Only blank values are ever written; nothing existing is overwritten.
"""

import json

import frappe

from event_bookings.utils.status import CANCELLED, STATUS_ORDER

CONFIRMED_OR_LATER = STATUS_ORDER[STATUS_ORDER.index("Confirmed"):]


def execute():
	bookings = frappe.get_all(
		"Event Booking",
		filters={"docstatus": ("<", 2)},
		fields=["name", "booking_status", "modified", "confirmed_on", "cancelled_on"],
		limit_page_length=0,
	)
	if not bookings:
		return

	history = _status_change_dates([b.name for b in bookings])

	for booking in bookings:
		update = {}

		if booking.booking_status in CONFIRMED_OR_LATER and not booking.confirmed_on:
			update["confirmed_on"] = _pick(history, booking, CONFIRMED_OR_LATER)

		if booking.booking_status == CANCELLED and not booking.cancelled_on:
			update["cancelled_on"] = _pick(history, booking, [CANCELLED])

		if update:
			frappe.db.set_value("Event Booking", booking.name, update, update_modified=False)

	frappe.db.commit()


def _pick(history, booking, statuses):
	"""Earliest recorded move into any of *statuses*, else the booking's modified date."""
	dates = [
		changed_on
		for status, changed_on in history.get(booking.name, [])
		if status in statuses
	]
	return min(dates) if dates else frappe.utils.getdate(booking.modified)


def _status_change_dates(names):
	"""Map booking name -> [(new_status, date), ...] from Version history."""
	if not names:
		return {}

	rows = frappe.get_all(
		"Version",
		filters={"ref_doctype": "Event Booking", "docname": ("in", names)},
		fields=["docname", "data", "creation"],
		limit_page_length=0,
	)

	history = {}
	for row in rows:
		try:
			data = json.loads(row.data or "{}")
		except (ValueError, TypeError):
			continue
		# changed entries are [fieldname, old_value, new_value]
		for change in data.get("changed") or []:
			if len(change) == 3 and change[0] == "booking_status" and change[2]:
				history.setdefault(row.docname, []).append(
					(change[2], frappe.utils.getdate(row.creation))
				)
	return history
