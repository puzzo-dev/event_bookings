// Copyright (c) 2026, Avril Beetails and contributors
// For license information, please see license.txt

frappe.ui.form.on("Event Booking", {
    refresh(frm) {
        if (!frm.is_new() && !frm.doc.quotation && !frm.doc.sales_order) {
            frm.add_custom_button(__('Create Quotation'), function() {
                frappe.model.open_mapped_doc({
                    method: "event_bookings.event_bookings.doctype.event_booking.event_booking.make_quotation",
                    frm: frm
                });
            }, __('Actions'));
        }
    },
});
