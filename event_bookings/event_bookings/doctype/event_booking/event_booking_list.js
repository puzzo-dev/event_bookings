// The booking status is what the pill shows — on the list and on the form.
//
// frappe.get_indicator is shared by both, and the form toolbar calls it for the
// pill beside the document name. Without the two flags below it short-circuits
// to "Draft" or "Cancelled" on docstatus alone and never reaches get_indicator,
// which is why a booking's real status was invisible on its own form.
//
// booking_status is read-only and hidden on the form now: it is set by the
// lifecycle, not typed, so this pill is the only place it is shown.

frappe.listview_settings["Event Booking"] = {
	// The list only fetches the fields it renders as columns, and
	// booking_status is no longer one — it is the pill instead. Without this it
	// is simply not in the row data and every pill reads "undefined".
	add_fields: ["booking_status"],

	// Both are needed. get_indicator is consulted after the docstatus
	// short-circuits, so these are what let it run for a draft or a cancelled
	// booking at all.
	has_indicator_for_draft: 1,
	has_indicator_for_cancelled: 1,

	get_indicator(doc) {
		if (!doc.booking_status) {
			// Nothing to show rather than an empty pill; frappe.get_indicator
			// falls through to its own defaults when this returns nothing.
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
		}[doc.booking_status] || "grey";

		return [__(doc.booking_status), colour, `booking_status,=,${doc.booking_status}`];
	},
};
