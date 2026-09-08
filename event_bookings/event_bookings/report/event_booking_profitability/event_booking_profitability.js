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
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
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
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			// Cancelled is omitted deliberately: like ERPNext reports, cancelled
			// bookings are excluded from this report entirely.
			options: "\nNew\nQuoted\nInvoiced\nConfirmed\nPaid\nExecuted",
		},
	]
};
