// The status pill, done the way ERPNext does it for Sales Order and Sales
// Invoice: one read-only field the lifecycle maintains, surfaced as the
// indicator rather than as a second column.
//
// add_fields is not a workaround — sales_order_list.js lists "status" there for
// the same reason. Frappe fetches a field named literally `status` for the list
// whether or not it is a column (get_fields_in_list_view), and drops it from the
// columns when the doctype has an indicator (setup_columns), so ERPNext gets
// both for free from the name. This field is booking_status, so it asks.
//
// No has_indicator_for_draft / has_indicator_for_cancelled. ERPNext does not
// override those, and neither should this: a draft reads "Draft" and a
// cancelled document reads "Cancelled", which is true and is what every other
// submittable doctype on the site does. booking_status is what a *submitted*
// booking is doing, and that is when this runs.

frappe.listview_settings["Event Booking"] = {
	add_fields: ["booking_status"],

	get_indicator(doc) {
		if (!doc.booking_status) {
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
