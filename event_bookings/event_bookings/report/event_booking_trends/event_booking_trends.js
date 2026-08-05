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
			"fieldname": "fiscal_year",
			"label": __("Fiscal Year"),
			"fieldtype": "Link",
			"options": "Fiscal Year",
			"default": erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
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
			"fieldname": "group_by",
			"label": __("Group By"),
			"fieldtype": "Select",
			"options": "\nEvent Type",
			"default": ""
		},
		{
			"fieldname": "date_field",
			"label": __("Date Field"),
			"fieldtype": "Select",
			"options": "booking_date\nevent_date",
			"default": "booking_date",
			"reqd": 1
		}
	]
};
