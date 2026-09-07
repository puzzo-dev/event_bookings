"""Backfill Event Booking.customer from the retired party model.

Quotation-first pivot: bookings now carry a single Customer link. This patch
migrates existing rows — additive and idempotent; the legacy party columns
are kept (hidden) so no data is destroyed.

- party_type = "Customer" → customer = party_name
- party_type = "Lead"     → convert via make_customer_from_lead (reusing an
                            existing Customer linked to the lead), then link
- Individual / Organization / empty rows → left untouched, logged for manual
  follow-up (no Customer equivalent; party_name data preserved)
"""

import frappe

from event_bookings.utils.erpnext_bridge import is_erpnext_installed, make_customer_from_lead


def execute():
	if not is_erpnext_installed():
		# Plain-Frappe sites have no Customer doctype — nothing to backfill.
		return

	# 1. Customer-party bookings → direct copy
	frappe.db.sql(
		"""
		UPDATE `tabEvent Booking`
		SET customer = party_name
		WHERE IFNULL(customer, '') = ''
		  AND party_type = 'Customer'
		  AND IFNULL(party_name, '') != ''
		"""
	)

	# 2. Lead-party bookings → convert (reuse existing Customer by lead_name)
	leads = frappe.get_all(
		"Event Booking",
		filters={"party_type": "Lead", "customer": ("is", "not set")},
		fields=["name", "party_name"],
		limit_page_length=0,
	)
	converted = 0
	for row in leads:
		if not row.party_name:
			continue
		try:
			existing = frappe.db.get_value("Customer", {"lead_name": row.party_name}, "name")
			if existing:
				customer = existing
			else:
				customer = make_customer_from_lead(row.party_name).insert(
					ignore_permissions=True
				).name
			frappe.db.set_value(
				"Event Booking", row.name, "customer", customer, update_modified=False
			)
			converted += 1
		except Exception:
			frappe.log_error(
				title=f"event_bookings backfill: failed to convert Lead {row.party_name} "
				f"for booking {row.name}",
				message=frappe.get_traceback(),
			)

	# 3. Rows with no customer equivalent — informational only
	unresolved = frappe.db.count(
		"Event Booking",
		filters={
			"customer": ("is", "not set"),
			"party_type": ("in", ["Individual", "Organization"]),
		},
	)
	if converted or unresolved:
		frappe.logger().info(
			f"event_bookings customer backfill: {converted} lead booking(s) converted, "
			f"{unresolved} Individual/Organization booking(s) keep legacy party data "
			"(no Customer equivalent — manual follow-up)"
		)

	frappe.db.commit()
