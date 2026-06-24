// Conditionally show/hide ERPNext and HRMS workspace sections
// based on whether those apps are installed on this site.
// frappe.boot.installed_apps is populated server-side by Frappe.
frappe.provide("event_bookings.workspace");

(function () {
	const ERPNEXT_SECTIONS = ["Sales / Selling", "Buying / Purchase"];

	// Reports that require ERPNext (revenue figures come from Quotation/SO/SI)
	const ERPNEXT_REPORTS = [
		"Event Booking Profitability",
		"Event Booking Pipeline",
		"Event Revenue Trend",
	];

	// Charts that require ERPNext (count + amount from SI/Quotation data)
	const ERPNEXT_CHARTS = [
		"Deals Completed",        // workspace label
		"Deals Lost",             // workspace label
		"Event Deals Completed",  // chart_name fallback
		"Event Deals Lost",       // chart_name fallback
	];

	function apply_conditions() {
		var installed = (frappe.boot && frappe.boot.installed_apps) || [];
		var has_erpnext = installed.indexOf("erpnext") !== -1;

		if (has_erpnext) return; // nothing to hide

		// Hide Card Break sections that belong to ERPNext
		$(".workspace-sidebar-list-item, .desk-sidebar-item").each(function () {
			var label = $(this).text().trim();
			if (ERPNEXT_SECTIONS.indexOf(label) !== -1) {
				$(this).closest(".sidebar-group, .workspace-sidebar-section").hide();
			}
		});

		// Hide ERPNext-only report links
		$("a.workspace-link, a[data-route]").each(function () {
			var text = $(this).text().trim();
			if (ERPNEXT_REPORTS.indexOf(text) !== -1) {
				$(this).closest("li, .workspace-link-item").hide();
			}
		});

		// Hide ERPNext-only charts — Frappe renders chart widgets with the
		// chart label as the heading inside .widget-title
		$(".widget.chart-widget .widget-head .widget-title").each(function () {
			if (ERPNEXT_CHARTS.indexOf($(this).text().trim()) !== -1) {
				$(this).closest(".widget.chart-widget").hide();
			}
		});
	}

	$(document).on("page-change", function () {
		var route = frappe.get_route ? frappe.get_route() : [];
		if (route[0] === "Workspaces") {
			// Delay slightly to let workspace finish rendering
			setTimeout(apply_conditions, 300);
		}
	});
})();
