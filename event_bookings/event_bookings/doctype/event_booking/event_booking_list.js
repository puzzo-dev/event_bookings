// The status pill, the way Sales Order and Sales Invoice do it: one read-only
// field the lifecycle maintains, surfaced as the indicator.
//
// Nothing else is needed. The field is named `status`, so Frappe fetches it for
// the list whether or not it is a column (get_fields_in_list_view) and drops it
// from the columns while the doctype has an indicator (setup_columns) — which
// is why in_list_view can stay on without the value appearing twice. The name
// is doing the work that an add_fields entry and a pair of
// has_indicator_for_* overrides used to.
//
// Draft and Cancelled still come from docstatus, as they do everywhere else on
// the site. This runs for a submitted booking, which is when the lifecycle
// status is the thing worth showing.

frappe.listview_settings["Event Booking"] = {
	get_indicator(doc) {
		if (!doc.status) {
			return null;
		}

		// The colours read as a progression: the deal is open (blue), waiting
		// on someone (orange), settled (green), finished (grey), or dead (red).
		const colour = {
			New: "blue",
			Quoted: "orange",
			Confirmed: "blue",
			Invoiced: "purple",
			Paid: "green",
			Executed: "grey",
			Cancelled: "red",
		}[doc.status] || "grey";

		return [__(doc.status), colour, `status,=,${doc.status}`];
	},
};
