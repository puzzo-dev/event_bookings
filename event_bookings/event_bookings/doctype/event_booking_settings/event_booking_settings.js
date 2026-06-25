// Copyright (c) 2026, Avril Beetails and contributors
// For license information, please see license.txt

frappe.ui.form.on("Event Booking Settings", {
	setup(frm) {
		// Restrict all Account link fields to the selected company so
		// cross-company account links are impossible at the UI level.
		const account_fields = [
			"default_cogs_account",
			"default_income_account",
			"default_damages_account",
		];
		account_fields.forEach((fieldname) => {
			frm.set_query(fieldname, () => ({
				filters: { company: frm.doc.company, is_group: 0 },
			}));
		});

		// Restrict all Warehouse link fields to the selected company.
		const warehouse_fields = [
			"default_warehouse",
			"events_warehouse",
			"damages_warehouse",
		];
		warehouse_fields.forEach((fieldname) => {
			frm.set_query(fieldname, () => ({
				filters: { company: frm.doc.company, is_group: 0 },
			}));
		});

	},
});
