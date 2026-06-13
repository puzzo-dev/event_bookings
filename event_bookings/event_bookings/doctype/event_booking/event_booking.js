// Copyright (c) 2026, Avril Beetails and contributors
// For license information, please see license.txt

frappe.ui.form.on("Event Booking", {
	refresh(frm) {
		if (!frm.is_new() && !frm.doc.quotation && !frm.doc.sales_order) {
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

		if (!frm.is_new() && frm.doc.booking_status === "Executed") {
			frm.add_custom_button(
				__("Record Damages"),
				function () {
					event_bookings.show_damage_dialog(frm);
				},
				__("Actions")
			);
		}
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
