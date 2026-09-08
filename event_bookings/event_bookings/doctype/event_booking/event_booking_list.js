// Colour the booking status in the list view.
//
// This only ever existed on the production branches, so it was never carried
// into develop and every sync back from develop dropped it. It also still
// listed "Negotiating" and "In Preparation", two states the status model no
// longer has — a booking in any current state fell through to grey.
//
// The colours read as a progression: the deal is open (blue), waiting on
// someone (orange), settled (green), finished (grey), or dead (red).

frappe.listview_settings["Event Booking"] = {
	get_indicator(doc) {
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
