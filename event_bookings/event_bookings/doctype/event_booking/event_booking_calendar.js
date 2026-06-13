frappe.views.calendar["Event Booking"] = {
	field_map: {
		start: "event_date",
		end: "event_date",
		id: "name",
		title: "event_name",
		status: "booking_status",
	},
	order_by: "event_date",
	get_events_method: "frappe.client.get_list",
	filters: [
		{
			fieldtype: "Select",
			fieldname: "booking_status",
			options:
				"\nNew\nQuoted\nNegotiating\nConfirmed\nIn Preparation\nExecuted\nInvoiced\nPaid\nCancelled",
			label: __("Status"),
		},
	],
	get_css_class: function (data) {
		var status_map = {
			New: "default",
			Quoted: "warning",
			Negotiating: "warning",
			Confirmed: "success",
			"In Preparation": "info",
			Executed: "primary",
			Invoiced: "danger",
			Paid: "success",
			Cancelled: "dark",
		};
		return status_map[data.booking_status] || "default";
	},
};
