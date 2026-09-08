"""Advance bookings stranded by the broken payment hook.

``_eb_advance_from_sales_invoice`` called ``set_status(update_status=True)``, a
keyword ERPNext's ``SalesInvoice.set_status`` does not accept. Every invocation
raised TypeError, and ``on_payment_entry_submit``'s except block swallowed it,
so no Payment Entry ever advanced a booking to Confirmed or Paid for the whole
life of the feature.

Repairing the hook does not repair history: nothing re-fires for a Payment
Entry that was already submitted. This patch replays the decision once, from
the invoices' *current* settled state, which is the same source of truth the
fixed hook uses.

Safety, per the app's data rules:
- Forward-only. ``advance_booking_status`` refuses to move a booking backwards
  or to touch a Cancelled one, so a manual override is never overwritten.
- Idempotent. A second run finds every booking already at or past its target
  and changes nothing.
- Auditable. The status write goes through the same helper as live automation,
  which stamps a timeline comment naming this patch as the cause.
- Additive. No schema change, no bulk rewrite; bookings whose invoices are
  genuinely unpaid are left exactly as they are.
"""

import frappe

from event_bookings.utils.status import advance_booking_status

# The statuses an invoice reports once money has actually moved.
PARTLY_PAID = ("Partly Paid", "Partly Paid and Discounted")


def execute():
	invoices = frappe.get_all(
		"Sales Invoice",
		filters={
			"docstatus": 1,
			"event_booking": ("is", "set"),
			"status": ("in", list(PARTLY_PAID) + ["Paid"]),
		},
		fields=["name", "event_booking", "status"],
		limit_page_length=0,
	)

	advanced = 0
	for si in invoices:
		if not frappe.db.exists("Event Booking", si.event_booking):
			continue

		target = "Paid" if si.status == "Paid" else "Confirmed"
		# `status`, not `booking_status`. This patch straddled the rename: it
		# read the column by its old name here and then called
		# advance_booking_status, which reads the new one. Ordered before the
		# rename it found an empty column and silently repaired nothing;
		# ordered after it, the old column was gone and the migration aborted.
		# rename_booking_status_to_status is now sequenced immediately before
		# this patch, so the new name is the only one that exists by the time
		# it runs, and both halves of the patch agree.
		before = frappe.db.get_value("Event Booking", si.event_booking, "status")
		if before == target:
			continue

		try:
			advance_booking_status(
				si.event_booking,
				target,
				reason=(
					f"Sales Invoice {si.name} is {si.status} — resynced by patch "
					"(the payment hook previously failed silently)"
				),
			)
		except Exception:
			# One unhappy booking must not abort the migration.
			frappe.log_error(
				message=(
					f"Sales Invoice: {si.name}\n"
					f"Event Booking: {si.event_booking}\n\n"
					f"{frappe.get_traceback()}"
				),
				title="Event Bookings: stranded payment resync failed",
			)
			continue

		after = frappe.db.get_value("Event Booking", si.event_booking, "status")
		if after != before:
			advanced += 1

	if advanced:
		print(f"resync_stranded_invoice_payments: advanced {advanced} booking(s)")
