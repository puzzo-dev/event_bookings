// Copyright (c) 2026, Avril Beetails and contributors
// For license information, please see license.txt

// Quotation-first flow (user-confirmed): an Event Booking is created FROM an
// accepted Quotation (Quotation → Create → Event Booking). The old "Create
// Quotation" button is removed — quotations are created first, then linked.
// Create Sales Order is always available (works with or without a quotation).

frappe.ui.form.on("Event Booking", {
    refresh(frm) {
        if (frm.fields_dict.special_requirements && frm.fields_dict.special_requirements.$input) {
            frm.fields_dict.special_requirements.$input.css('height', '100px');
        }

        if (!frm.is_new()) {
            // Refresh button — reloads the form to pick up linked-document
            // changes (e.g. Sales Order/Sales Invoice created and linked
            // server-side by ERPNext hooks).
            frm.add_custom_button(__('Refresh'), function() {
                frm.reload_doc();
            });

            // Create Sales Order — always available, with or without a
            // linked quotation. The server-side mapper copies quotation
            // items if a quotation exists, otherwise creates a blank SO.
            if (!frm.doc.sales_order) {
                frm.add_custom_button(__('Sales Order'), function() {
                    frappe.model.open_mapped_doc({
                        method: "event_bookings.event_bookings.doctype.event_booking.event_booking.make_sales_order",
                        source_name: frm.doc.name,
                        frm: frm
                    });
                }, __('Create'));
            }

            // Create Sales Invoice from the linked Sales Order.
            if (frm.doc.sales_order && !frm.doc.sales_invoice) {
                frm.add_custom_button(__('Sales Invoice'), function() {
                    frappe.model.open_mapped_doc({
                        method: "erpnext.selling.doctype.sales_order.sales_order.make_sales_invoice",
                        source_name: frm.doc.sales_order,
                        frm: frm
                    });
                }, __('Create'));
            }

            // Create Project from the Event Booking.
            if (!frm.doc.project) {
                frm.add_custom_button(__('Project'), function() {
                    frappe.model.open_mapped_doc({
                        method: "event_bookings.event_bookings.doctype.event_booking.event_booking.make_project",
                        source_name: frm.doc.name,
                        frm: frm
                    });
                }, __('Create'));
            }

            // Create Stock Entry — opens a dialog to choose the type, then
            // creates a Stock Entry with event_booking, company, cost_center
            // and default warehouse prefilled from Event Booking Settings.
            _add_stock_entry_button(frm);

            // Render the items table (from linked Quotation or Sales Order)
            _render_items_table(frm);
        }
    },
});

function _add_stock_entry_button(frm) {
    if (!frappe.erpnext) return;

    frm.add_custom_button(__('Stock Entry'), function() {
        let dialog = new frappe.ui.Dialog({
            title: __('Create Stock Entry'),
            fields: [
                {
                    fieldname: 'stock_entry_type',
                    label: __('Stock Entry Type'),
                    fieldtype: 'Select',
                    options: ['Material Issue', 'Material Transfer', 'Material Transfer for Manufacture'],
                    default: 'Material Issue',
                    reqd: 1
                }
            ]
        });

        dialog.set_primary_action(__('Create'), function(values) {
            frappe.model.open_mapped_doc({
                method: "event_bookings.event_bookings.doctype.event_booking.event_booking.make_stock_entry",
                source_name: frm.doc.name,
                args: {
                    stock_entry_type: values.stock_entry_type
                },
                frm: frm
            });
            dialog.hide();
        });

        dialog.show();
    }, __('Create'));
}

function _render_items_table(frm) {
    let wrapper = frm.get_field("items_html").$wrapper;
    wrapper.empty();

    // Fetch items from Sales Order if linked, otherwise from Quotation
    let method, source_name;
    if (frm.doc.sales_order) {
        method = "event_bookings.event_bookings.doctype.event_booking.event_booking.get_items_from_sales_order";
        source_name = frm.doc.sales_order;
    } else if (frm.doc.quotation) {
        method = "event_bookings.event_bookings.doctype.event_booking.event_booking.get_items_from_quotation";
        source_name = frm.doc.quotation;
    } else {
        wrapper.html('<p class="text-muted small">No quotation or sales order linked.</p>');
        return;
    }

    // refresh() fires on form load, after every save, and on every tab switch,
    // so without this the items table costs a server round trip each time.
    // Keyed on the source document: linking a different Quotation or Sales
    // Order changes the key and refetches. The items themselves come from a
    // submitted document, which cannot change without an amend (and an amend
    // produces a new name, hence a new key), so the cached copy cannot go
    // stale while the form is open.
    const cache_key = method + ":" + source_name;
    if (frm.__eb_items_key === cache_key && frm.__eb_items_html) {
        wrapper.html(frm.__eb_items_html);
        return;
    }

    frappe.call({
        method: method,
        args: { quotation_name: source_name, sales_order_name: source_name },
        callback: function(r) {
            if (!r.message || !r.message.length) {
                const empty = '<p class="text-muted small">No items found.</p>';
                frm.__eb_items_key = cache_key;
                frm.__eb_items_html = empty;
                wrapper.html(empty);
                return;
            }

            let rows = r.message.map(item => `
                <tr>
                    <td>${item.item_code || ''}</td>
                    <td>${item.item_name || ''}</td>
                    <td class="text-right">${item.qty || 0}</td>
                    <td>${item.uom || ''}</td>
                    <td class="text-right">${frappe.format(item.rate, {fieldtype: "Currency"})}</td>
                    <td class="text-right">${frappe.format(item.amount, {fieldtype: "Currency"})}</td>
                </tr>
            `).join('');

            const html = `
                <table class="table table-bordered table-sm">
                    <thead>
                        <tr>
                            <th>Item Code</th>
                            <th>Item Name</th>
                            <th class="text-right">Qty</th>
                            <th>UOM</th>
                            <th class="text-right">Rate</th>
                            <th class="text-right">Amount</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            `;
            frm.__eb_items_key = cache_key;
            frm.__eb_items_html = html;
            wrapper.html(html);
        }
    });
}
