// Copyright (c) 2026, Avril Beetails and contributors
// For license information, please see license.txt

frappe.ui.form.on("Event Booking", {
    refresh(frm) {
        if (frm.fields_dict.special_requirements && frm.fields_dict.special_requirements.$input) {
            frm.fields_dict.special_requirements.$input.css('height', '100px');
        }
        if (!frm.is_new()) {
            // Convert Lead to Customer — only when party is a Lead
            if (frm.doc.party_type === "Lead") {
                frm.add_custom_button(__('Convert Lead to Customer'), function() {
                    frappe.db.get_value("Customer", { lead_name: frm.doc.party_name }, "name").then(r => {
                        if (r && r.message && r.message.name) {
                            // Already a Customer — just link silently
                            _do_convert(frm, null);
                        } else {
                            frappe.confirm(
                                __('Convert Lead <b>{0}</b> to a Customer and update this booking?',
                                    [frm.doc.party_name]),
                                () => _do_convert(frm, null)
                            );
                        }
                    });
                }, __('Actions'));
            }

            if (!frm.doc.quotation && !frm.doc.sales_order) {
                frm.add_custom_button(__('Create Quotation'), function() {
                    if (frm.doc.party_type === "Lead") {
                        _prompt_lead_conversion(frm, function() {
                            frappe.model.open_mapped_doc({
                                method: "event_bookings.event_bookings.doctype.event_booking.event_booking.make_quotation",
                                frm: frm
                            });
                        });
                    } else {
                        frappe.model.open_mapped_doc({
                            method: "event_bookings.event_bookings.doctype.event_booking.event_booking.make_quotation",
                            frm: frm
                        });
                    }
                }, __('Actions'));
            }

            if (frm.doc.quotation && !frm.doc.sales_order) {
                frm.add_custom_button(__('Create Sales Order'), function() {
                    if (frm.doc.party_type === "Lead") {
                        _prompt_lead_conversion(frm, function() {
                            frappe.model.open_mapped_doc({
                                method: "erpnext.selling.doctype.quotation.quotation.make_sales_order",
                                source_name: frm.doc.quotation,
                                frm: frm
                            });
                        });
                    } else {
                        frappe.model.open_mapped_doc({
                            method: "erpnext.selling.doctype.quotation.quotation.make_sales_order",
                            source_name: frm.doc.quotation,
                            frm: frm
                        });
                    }
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

    party_type(frm) {
        frm.set_value("party_name", "");
    },
});

function _prompt_lead_conversion(frm, on_skip) {
    // Check if this Lead already has a Customer in the system — skip the dialog if so
    frappe.db.get_value("Customer", { lead_name: frm.doc.party_name }, "name").then(r => {
        if (r && r.message && r.message.name) {
            // Lead is already a Customer — silently link and proceed
            _do_convert(frm, on_skip);
        } else {
            _show_conversion_dialog(frm, on_skip);
        }
    });
}

function _do_convert(frm, on_skip) {
    frappe.call({
        method: "event_bookings.event_bookings.doctype.event_booking.event_booking.convert_lead_and_update_booking",
        args: { booking_name: frm.doc.name },
        freeze: true,
        freeze_message: __("Linking Customer..."),
        callback(r) {
            if (r.message) {
                const msg = r.message.already_existed
                    ? __("Booking linked to existing Customer: {0}", [r.message.customer])
                    : __("Lead converted to Customer: {0}", [r.message.customer]);
                frappe.show_alert({ message: msg, indicator: "green" }, 5);
                frm.reload_doc().then(() => on_skip && on_skip());
            }
        }
    });
}

function _show_conversion_dialog(frm, on_skip) {
    const d = new frappe.ui.Dialog({
        title: __("Lead Detected"),
        fields: [
            {
                fieldtype: "HTML",
                options: `<div class="alert alert-warning" style="margin-bottom:0">
                    <b>${__("Party is a Lead, not a Customer.")}</b><br>
                    ${__("Sales Orders and Invoices require a Customer. Would you like to convert <b>{0}</b> to a Customer now, or proceed with the Lead?", [frm.doc.party_name])}
                </div>`
            }
        ],
        primary_action_label: __("Convert to Customer & Proceed"),
        primary_action() {
            d.hide();
            _do_convert(frm, on_skip);
        },
        secondary_action_label: __("Proceed as Lead"),
        secondary_action() {
            d.hide();
            on_skip && on_skip();
        }
    });
    d.show();
}
