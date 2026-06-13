import frappe

from event_bookings.utils.print_format_html import EVENT_BOOKING_CONFIRMATION_HTML


def update():
	doc = frappe.get_doc("Print Format", "Event Booking Confirmation")
	doc.html = EVENT_BOOKING_CONFIRMATION_HTML
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	print("Force updated Print Format!")
