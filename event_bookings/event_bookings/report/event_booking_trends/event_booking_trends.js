// Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.query_reports["Event Booking Trends"] = {
	"filters": [
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company"),
			"reqd": 1
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -11),
			"reqd": 1
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		},
		{
			"fieldname": "period",
			"label": __("Period"),
			"fieldtype": "Select",
			"options": "Weekly\nMonthly\nQuarterly\nYearly",
			"default": "Monthly",
			"reqd": 1
		},
		{
			"fieldname": "based_on",
			"label": __("Based On"),
			"fieldtype": "Select",
			"options": "Revenue\nCount",
			"default": "Revenue",
			"reqd": 1
		},
		{
			"fieldname": "date_field",
			"label": __("Date Field"),
			"fieldtype": "Select",
			"options": "event_date\nbooking_date",
			"default": "event_date",
			"reqd": 1
		}
	]
};
