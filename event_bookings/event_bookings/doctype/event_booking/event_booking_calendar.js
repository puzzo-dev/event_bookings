frappe.views.calendar["Event Booking"] = {
	field_map: {
		start: "event_date",
		end: "event_date",
		id: "name",
		title: "event_name",
		status: "booking_status",
	},
	style_map: {
		"New": "info",
		"Quoted": "info",
		"Negotiating": "warning",
		"Confirmed": "primary",
		"In Preparation": "primary",
		"Executed": "default",
		"Invoiced": "success",
		"Paid": "success",
		"Cancelled": "danger",
	},
	get_events_method: "event_bookings.event_bookings.doctype.event_booking.event_booking.get_calendar_events",
};
