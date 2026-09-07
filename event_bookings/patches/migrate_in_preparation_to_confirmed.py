import frappe


def execute():
	"""Migrate bookings in removed statuses to their closest equivalent.

	- 'In Preparation' → 'Confirmed' (preparations are implied by confirmation)
	- 'Negotiating'    → 'Quoted'     (negotiation happens while the quote is active)

	Both statuses were removed per user request — no part of the system
	automatically detects or manages them. This is idempotent: running it
	again does nothing once no rows with the old statuses remain.
	"""
	migrations = [
		("In Preparation", "Confirmed"),
		("Negotiating", "Quoted"),
	]
	for old_status, new_status in migrations:
		count = frappe.db.count("Event Booking", {"booking_status": old_status})
		if count:
			frappe.db.set_value(
				"Event Booking",
				{"booking_status": old_status},
				"booking_status",
				new_status,
				update_modified=False,
			)
			frappe.log(
				title=f"Event Bookings: migrated {old_status} → {new_status}",
				message=f"{count} booking(s) updated.",
			)
