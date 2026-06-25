"""
Patch: make_settings_single
Converts Event Booking Settings from a per-company DocType to a Single DocType.

Reads the first existing per-company settings record, migrates its values into
tabSingles, then drops the old table (bench migrate handles the schema changes).

Safe to re-run — guarded by an existence check on the old table.
"""
import frappe


def execute():
	# Only run when the old per-company table still exists
	if not frappe.db.table_exists("tabEvent Booking Settings"):
		return

	carried_fields = (
		"default_warehouse",
		"events_warehouse",
		"damages_warehouse",
		"default_cogs_account",
		"default_income_account",
		"default_damages_account",
		"pre_event_reminder_days",
		"require_review",
		"enable_whatsapp",
	)

	# Use the first company record as the source of truth
	rows = frappe.db.sql(
		"SELECT * FROM `tabEvent Booking Settings` LIMIT 1",
		as_dict=True,
	)

	if rows:
		source = rows[0]
		for field in carried_fields:
			value = source.get(field)
			if value is None:
				continue
			existing = frappe.db.sql(
				"SELECT value FROM `tabSingles` WHERE doctype = 'Event Booking Settings' AND field = %s",
				field,
			)
			if not existing:
				frappe.db.sql(
					"INSERT INTO `tabSingles` (doctype, field, value) VALUES ('Event Booking Settings', %s, %s)",
					(field, value),
				)

	# Drop the old per-company table so bench migrate creates the Singles-backed record
	frappe.db.sql("DROP TABLE IF EXISTS `tabEvent Booking Settings`")
	frappe.db.commit()
