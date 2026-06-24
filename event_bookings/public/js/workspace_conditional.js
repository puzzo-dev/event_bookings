// Conditionally show/hide ERPNext and HRMS workspace sections
// based on whether those apps are installed on this site.
frappe.provide("event_bookings.workspace");

(function () {
	const ERPNEXT_SECTIONS = ["Sales / Selling", "Buying / Purchase"];
	const ERPNEXT_REPORTS = ["Event Booking Profitability", "Event Booking Pipeline"];

	function apply_conditions() {
		var installed = (frappe.boot && frappe.boot.installed_apps) || [];
		var has_erpnext = installed.indexOf("erpnext") !== -1;

		if (has_erpnext) return; // nothing to hide

		// Hide card-break sections that require ERPNext
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
	}

	$(document).on("page-change", function () {
		var route = frappe.get_route ? frappe.get_route() : [];
		if (route[0] === "Workspaces") {
			// Delay slightly to let workspace finish rendering
			setTimeout(apply_conditions, 300);
		}
	});
})();
