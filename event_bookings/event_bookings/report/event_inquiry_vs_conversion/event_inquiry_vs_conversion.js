// Copyright (c) 2026, I-Varse Technologies NG and contributors
// For license information, please see license.txt

frappe.query_reports["Event Inquiry vs Conversion"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default:
				typeof erpnext !== "undefined" && erpnext.utils
					? erpnext.utils.get_fiscal_year(frappe.datetime.get_today())
					: "",
			reqd: 1,
		},
		{
			fieldname: "period",
			label: __("Period"),
			fieldtype: "Select",
			options: "Monthly\nQuarterly\nYearly",
			default: "Monthly",
			reqd: 1,
		},
	],
};
