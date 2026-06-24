frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Event Inquiry vs Conversion"] = {
	method: "event_bookings.utils.dashboard_charts.get_inquiry_conversion_chart",
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "timespan",
			label: __("Timespan"),
			fieldtype: "Select",
			options: [
				"",
				"This Month",
				"This Quarter",
				"This Year",
				"Last Month",
				"Last Quarter",
				"Last 6 Months",
				"Last Year",
				"Date Range",
			].join("\n"),
			default: "Last 6 Months",
		},
		{
			fieldname: "start_date",
			label: __("From Date"),
			fieldtype: "Date",
			depends_on: "eval:doc.timespan == 'Date Range'",
		},
		{
			fieldname: "end_date",
			label: __("To Date"),
			fieldtype: "Date",
			depends_on: "eval:doc.timespan == 'Date Range'",
		},
	],
};
