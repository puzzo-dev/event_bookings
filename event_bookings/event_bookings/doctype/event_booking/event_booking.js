// Copyright (c) 2026, Avril Beetails and contributors
// For license information, please see license.txt

frappe.ui.form.on("Event Booking", {
    refresh(frm) {
        if (frm.fields_dict.special_requirements && frm.fields_dict.special_requirements.$input) {
            frm.fields_dict.special_requirements.$input.css('height', '100px');
        }
        if (!frm.is_new()) {
            if (!frm.doc.quotation && !frm.doc.sales_order) {
                frm.add_custom_button(__('Create Quotation'), function() {
                    frappe.model.open_mapped_doc({
                        method: "event_bookings.event_bookings.doctype.event_booking.event_booking.make_quotation",
                        frm: frm
                    });
                }, __('Actions'));
            }

            if (!frm.doc.project) {
                frm.add_custom_button(__('Create Project'), function() {
                    frappe.model.open_mapped_doc({
                        method: "event_bookings.event_bookings.doctype.event_booking.event_booking.make_project",
                        frm: frm
                    });
                }, __('Actions'));
            }
        }
    },

    event_end_time(frm) {
        if (frm.doc.event_end_time && frm.doc.event_timing) {
            if (new Date(frm.doc.event_end_time) <= new Date(frm.doc.event_timing)) {
                frappe.msgprint(__('Event End Time must be after Event Timing.'));
                frm.set_value('event_end_time', null);
            }
        }
    },
});
