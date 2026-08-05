// Copyright (c) 2026, Avril Beetails and contributors
// For license information, please see license.txt

frappe.ui.form.on("Event Booking", {
    refresh(frm) {
        if (frm.fields_dict.special_requirements && frm.fields_dict.special_requirements.$input) {
            frm.fields_dict.special_requirements.$input.css('height', '100px');
        }
        _render_items_html(frm);
        if (!frm.is_new()) {
            if (!frm.doc.quotation && !frm.doc.sales_order) {
                frm.add_custom_button(__('Create Quotation'), function() {
                    frappe.model.open_mapped_doc({
                        method: "event_bookings.event_bookings.doctype.event_booking.event_booking.make_quotation",
                        frm: frm
                    });
                }, __('Actions'));
            }

            if (!frm.doc.sales_order) {
                frm.add_custom_button(__('Create Sales Order'), function() {
                    frappe.model.open_mapped_doc({
                        method: "event_bookings.event_bookings.doctype.event_booking.event_booking.make_sales_order",
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

    party_type(frm) {
        frm.set_value("party_name", "");
    },
});

function _render_items_html(frm) {
    const field = frm.get_field("items_html");
    if (!field || !field.wrapper) return;

    const source = frm.doc.sales_order || frm.doc.quotation;
    const $wrapper = $(field.wrapper);

    if (!source) {
        $wrapper.empty();
        return;
    }

    const method = frm.doc.sales_order
        ? "event_bookings.event_bookings.doctype.event_booking.event_booking.get_items_from_sales_order"
        : "event_bookings.event_bookings.doctype.event_booking.event_booking.get_items_from_quotation";

    const args = frm.doc.sales_order
        ? { sales_order_name: source }
        : { quotation_name: source };

    frappe.call({
        method: method,
        args: args,
        callback(r) {
            if (!r.message || !r.message.length) {
                $wrapper.html("<p class='text-muted small'>" + __("No items found.") + "</p>");
                return;
            }
            let html = "<table class='table table-bordered table-sm'>"
                + "<thead><tr>"
                + "<th>" + __("Item") + "</th>"
                + "<th class='text-right'>" + __("Qty") + "</th>"
                + "<th class='text-right'>" + __("Rate") + "</th>"
                + "<th class='text-right'>" + __("Amount") + "</th>"
                + "</tr></thead><tbody>";
            for (const item of r.message) {
                html += "<tr>"
                    + "<td>" + (item.item_name || item.item_code || "") + "</td>"
                    + "<td class='text-right'>" + (item.qty || 0) + "</td>"
                    + "<td class='text-right'>" + frappe.format(item.rate, {fieldtype: "Currency"}) + "</td>"
                    + "<td class='text-right'>" + frappe.format(item.amount, {fieldtype: "Currency"}) + "</td>"
                    + "</tr>";
            }
            html += "</tbody></table>";
            $wrapper.html(html);
        }
    });
}
