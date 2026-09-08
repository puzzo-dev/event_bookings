"""Populate Items Used on bookings that already have tagged Stock Entries.

Items Used became a derived table: it is rebuilt whenever a Stock Entry tagged
with an Event Booking is submitted or cancelled. Bookings that were delivered
before that existed have the Stock Entries but not the rows, so the table would
read empty for them until someone happened to re-save an entry — on exactly the
historical bookings nobody is going to touch again.

Only bookings with at least one submitted, tagged Stock Entry are rebuilt.
Bookings without one keep whatever their table holds: those rows were typed in
by hand under the field's old meaning, and there is no stock movement to
replace them with. Deleting them would destroy the only record of what an old
event used, so they are left alone and counted in the log instead.
"""

import frappe

from event_bookings.utils.stock_movements import sync_booking


def execute():
	if not frappe.db.has_column("Stock Entry", "event_booking"):
		# The accounting dimension has not been created yet; nothing to project.
		return

	bookings = frappe.db.sql_list(
		"""
		SELECT DISTINCT booking FROM (
			SELECT se.event_booking AS booking
			FROM `tabStock Entry` se
			WHERE se.docstatus = 1 AND IFNULL(se.event_booking, '') != ''
			UNION
			SELECT sed.event_booking AS booking
			FROM `tabStock Entry Detail` sed
			INNER JOIN `tabStock Entry` se ON se.name = sed.parent
			WHERE se.docstatus = 1 AND IFNULL(sed.event_booking, '') != ''
		) tagged
		"""
	)

	rebuilt = rows = 0
	for booking in bookings:
		if not frappe.db.exists("Event Booking", booking):
			continue
		count = sync_booking(booking)
		rebuilt += 1
		rows += count

	legacy = frappe.db.sql(
		"""
		SELECT COUNT(DISTINCT si.parent)
		FROM `tabService Item` si
		WHERE si.parenttype = 'Event Booking'
		  AND si.parentfield = 'event_items'
		  AND IFNULL(si.stock_entry, '') = ''
		"""
	)[0][0]

	frappe.db.commit()

	message = f"Rebuilt Items Used on {rebuilt} booking(s) from {rows} stock movement line(s)."
	if legacy:
		message += (
			f"\n\n{legacy} booking(s) still hold hand-entered rows with no Stock Entry "
			"behind them. They pre-date the derived table and were left untouched — "
			"there is no stock movement to replace them with, and they are the only "
			"record of what those events used. They will be replaced the first time a "
			"Stock Entry is tagged to those bookings."
		)
	frappe.log_error(title="Event Bookings: Items Used backfill", message=message)
