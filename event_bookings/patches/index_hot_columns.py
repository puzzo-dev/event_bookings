"""Index the columns the reports, hooks and schedulers filter on.

None of these were indexed, and every one is on a path that runs repeatedly:

  Event Booking.booking_status   — every report, chart and number card
  Event Booking.event_date       — the daily scheduler and the trends reports
  Event Booking.company          — the row-level partition on every list query
  Event Booking.event_planner    — the planner half of that same partition
  Event Booking.customer         — the connections view and the review flow
  Event Booking.quotation / sales_order / sales_invoice
                                 — the ERPNext hooks resolve a booking from its
                                   linked document on every submit and cancel
  Stock Entry.event_booking      — the Items Used projection, on every save of
                                   a tagged entry and on the backfill

Stock Entry belongs to ERPNext, which this app does not own, so a patch is the
supported way to index it from outside. add_index is a no-op when the index
already exists.
"""

import frappe

# booking_status, event_date, company, customer and sales_invoice already carry
# search_index on the field, so Frappe indexes them itself — adding them again
# produced a second index on the same column, which costs writes and disk and
# buys no reads. Only what the field definitions miss is here.
_INDEXES = [
	("Event Booking", ["event_planner"]),
	("Event Booking", ["quotation"]),
	("Event Booking", ["sales_order"]),
	("Stock Entry", ["event_booking"]),
	("Stock Entry Detail", ["event_booking"]),
]


def execute():
	for doctype, fields in _INDEXES:
		if not frappe.db.table_exists(doctype):
			continue
		if not all(frappe.db.has_column(doctype, f) for f in fields):
			# The accounting dimension may not have created its columns yet.
			continue
		try:
			frappe.db.add_index(doctype, fields)
		except Exception:
			frappe.log_error(
				title=f"Event Bookings: could not add index on {doctype} {fields}",
				message=frappe.get_traceback(),
			)
