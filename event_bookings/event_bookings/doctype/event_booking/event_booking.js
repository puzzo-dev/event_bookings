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

    event_date(frm) {
        _sync_event_timing(frm);
    },

    event_time(frm) {
        _sync_event_timing(frm);
    },

    event_end_date(frm) {
        _sync_event_end_datetime(frm);
    },

    event_end_time(frm) {
        _sync_event_end_datetime(frm);
    },
});

function _sync_event_timing(frm) {
    if (frm.doc.event_date && frm.doc.event_time) {
        frm.set_value('event_timing', frm.doc.event_date + ' ' + frm.doc.event_time);
    }
}

function _sync_event_end_datetime(frm) {
    const end_date = frm.doc.event_end_date;
    const end_time = frm.doc.event_end_time;
    if (end_date && end_time) {
        frm.set_value('event_end_datetime', end_date + ' ' + end_time);
    }
}
