import frappe

from event_bookings.utils.print_format_html import EVENT_BOOKING_CONFIRMATION_HTML


def create_print_format():
	if not frappe.db.exists("Print Format", "Event Booking Confirmation"):
		doc = frappe.get_doc(
			{
				"doctype": "Print Format",
				"name": "Event Booking Confirmation",
				"doc_type": "Event Booking",
				"module": "Event Bookings",
				"custom_format": 1,
				"standard": "Yes",
				"print_format_builder": 0,
				"align_labels_right": 0,
				"show_section_headings": 0,
				"line_breaks": 0,
				"html": EVENT_BOOKING_CONFIRMATION_HTML,
			}
		)
		doc.insert()
		frappe.db.commit()
		print("Created Print Format: Event Booking Confirmation")
	else:
		print("Print Format already exists.")


# Run manually via: bench --site <site> execute event_bookings.create_print_format.create_print_format
# create_print_format()
