// Event Bookings — Quotation-first flow.
//
// An Event Booking is created FROM a submitted Quotation: this script adds a
// Create → Event Booking action to the Quotation form. The button only appears
// when the Quotation is submitted (docstatus=1) and no Event Booking has been
// created yet. The booking is born with the quotation linked, status "Quoted",
// and the Customer resolved from the quotation's party (Lead quotations are
// converted first, with a confirm dialog so nothing is created silently).

frappe.ui.form.on("Quotation", {
    refresh(frm) {
        // Button only on submitted quotations without an existing booking
        if (frm.is_new() || frm.doc.docstatus !== 1 || frm.doc.event_booking) {
            return;
        }

        frm.add_custom_button(__('Event Booking'), function() {
            if (frm.doc.quotation_to === "Lead") {
                frappe.db.get_value(
                    "Customer", { lead_name: frm.doc.party_name }, "name"
                ).then(r => {
                    if (r && r.message && r.message.name) {
                        // Lead already has a Customer — map straight away.
                        _open_mapped_booking(frm);
                    } else {
                        frappe.confirm(
                            __('Convert Lead <b>{0}</b> to a Customer and create the Event Booking?',
                                [frm.doc.party_name]),
                            () => _open_mapped_booking(frm)
                        );
                    }
                });
            } else {
                _open_mapped_booking(frm);
            }
        }, __('Create'));
    },
});

function _open_mapped_booking(frm) {
    frappe.model.open_mapped_doc({
        method: "event_bookings.event_bookings.doctype.event_booking.event_booking.make_event_booking",
        source_name: frm.doc.name,
        frm: frm
    });
}
