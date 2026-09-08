frappe.views.calendar["Event Booking"] = {
	field_map: {
		start: "event_date",
		end: "event_date",
		id: "name",
		title: "event_name",
		status: "status",
	},
	style_map: {
		"New": "info",
		"Quoted": "info",
		"Invoiced": "warning",
		"Confirmed": "primary",
		"Paid": "success",
		"Executed": "default",
		"Cancelled": "danger",
	},
	get_events_method: "event_bookings.event_bookings.doctype.event_booking.event_booking.get_calendar_events",
};
