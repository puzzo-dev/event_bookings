// Copyright (c) 2026, Avril Beetails and contributors
// For license information, please see license.txt

frappe.ui.form.on("Event Booking", {
	refresh(frm) {
		if (!frm.is_new()) {
			if (!frm.doc.quotation && !frm.doc.sales_order) {
				frm.add_custom_button(
					__("Create Quotation"),
					function () {
						frappe.model.open_mapped_doc({
							method: "event_bookings.event_bookings.doctype.event_booking.event_booking.make_quotation",
							frm: frm,
						});
					},
					__("Actions")
				);
			}

			if (!frm.doc.project) {
				frm.add_custom_button(
					__("Create Project"),
					function () {
						frappe.model.open_mapped_doc({
							method: "event_bookings.event_bookings.doctype.event_booking.event_booking.make_project",
							frm: frm,
						});
					},
					__("Actions")
				);
			}

			if (frm.doc.booking_status === "Executed") {
				frm.add_custom_button(
					__("Record Damages"),
					function () {
						event_bookings.show_damage_dialog(frm);
					},
					__("Actions")
				);
			}

			frm.add_custom_button(
				__("Fetch Items from Quotation"),
				function () {
					if (!frm.doc.quotation) {
						frappe.show_alert({
							message: __("Create a Quotation against this booking first."),
							indicator: "orange",
						});
						return;
					}
					frappe.call({
						method: "event_bookings.event_bookings.doctype.event_booking.event_booking.get_items_from_quotation",
						args: { quotation_name: frm.doc.quotation },
						callback: function (r) {
							render_items_table(frm, r.message, __("Quotation Items"));
						},
					});
				},
				__("Actions")
			);

			frm.add_custom_button(
				__("Fetch Items from Sales Order"),
				function () {
					if (!frm.doc.sales_order) {
						frappe.show_alert({
							message: __("Create a Sales Order against this booking first."),
							indicator: "orange",
						});
						return;
					}
					frappe.call({
						method: "event_bookings.event_bookings.doctype.event_booking.event_booking.get_items_from_sales_order",
						args: { sales_order_name: frm.doc.sales_order },
						callback: function (r) {
							render_items_table(frm, r.message, __("Sales Order Items"));
						},
					});
				},
				__("Actions")
			);
		}

		render_items_table(frm, [], "");
	},

	validate(frm) {
		if (frm.doc.event_end_time && frm.doc.event_time) {
			if (frm.doc.event_end_time <= frm.doc.event_time) {
				frappe.msgprint(__("Event End Time must be after Event Time."));
				frappe.validated = false;
			}
		}
	},
});

var event_bookings = {
	show_damage_dialog: function (frm) {
		let d = new frappe.ui.Dialog({
			title: __("Record Damaged Items"),
			fields: [
				{
					fieldname: "items",
					fieldtype: "Table",
					label: __("Damaged Items"),
					fields: [
						{
							fieldname: "item_code",
							fieldtype: "Link",
							options: "Item",
							label: __("Item"),
							in_list_view: 1,
							reqd: 1,
						},
						{
							fieldname: "qty_damaged",
							fieldtype: "Float",
							label: __("Qty Damaged"),
							in_list_view: 1,
							reqd: 1,
						},
						{
							fieldname: "rate",
							fieldtype: "Currency",
							label: __("Rate"),
							in_list_view: 1,
						},
					],
				},
			],
			primary_action_label: __("Submit"),
			primary_action: function (values) {
				frappe.call({
					method: "event_bookings.event_bookings.doctype.event_booking.event_booking.record_damages",
					args: {
						event_booking: frm.doc.name,
						items: values.items,
					},
					callback: function () {
						frm.reload_doc();
						d.hide();
					},
				});
			},
		});
		d.show();
	},
};

function render_items_table(frm, items, title) {
	let wrapper = frm.fields_dict.items_html;
	if (!wrapper) return;
	let html = "";
	if (title) {
		html += `<h5 style="margin-bottom: 10px;">${title}</h5>`;
	}
	if (items && items.length) {
		html += `
            <table class="table table-bordered" style="width: 100%; margin-top: 10px;">
                <thead>
                    <tr>
                        <th>${__("Item")}</th>
                        <th style="text-align: right;">${__("Qty")}</th>
                        <th style="text-align: right;">${__("Rate")}</th>
                        <th style="text-align: right;">${__("Amount")}</th>
                    </tr>
                </thead>
                <tbody>
                    ${items
						.map(
							(item) => `
                        <tr>
                            <td>${item.item_name || item.item_code}</td>
                            <td style="text-align: right;">${item.qty} ${item.uom || ""}</td>
                            <td style="text-align: right;">${format_currency(item.rate)}</td>
                            <td style="text-align: right;">${format_currency(item.amount)}</td>
                        </tr>
                    `
						)
						.join("")}
                </tbody>
            </table>
        `;
	} else {
		html += `<p class="text-muted" style="margin-top: 10px;">${__(
			"No items fetched yet. Use the Actions menu to fetch items from a linked Quotation or Sales Order."
		)}</p>`;
	}
	$(wrapper.wrapper).html(html);
}

function format_currency(value) {
	if (value == null) return "";
	return frappe.format(value, { fieldtype: "Currency" });
}
