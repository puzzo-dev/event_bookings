// Copyright (c) 2026, Avril Beetails and contributors
// For license information, please see license.txt

frappe.query_reports["Event Booking Profitability"] = {
	"filters": [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "event_type",
			label: __("Event Type"),
			fieldtype: "Link",
			options: "Event Type",
		},
		{
			fieldname: "booking_status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nNew\nQuoted\nNegotiating\nConfirmed\nIn Preparation\nExecuted\nInvoiced\nPaid\nCancelled",
		},
	]
};
