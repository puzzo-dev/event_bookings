"""
Patch: migrate_settings_to_per_company
Converts Event Booking Settings from a Single doctype record (stored in tabSingles)
to per-company records in the new tabEvent Booking Settings table.

Runs post_model_sync so the new table already exists when this executes.
Safe to re-run — all operations are guarded by existence checks.
"""
import frappe


def execute():
	if not frappe.db.exists("DocType", "Event Booking Settings"):
		return

	# Read legacy values from tabSingles (present when the doctype was issingle)
	old_values = {
		row.field: row.value
		for row in frappe.db.get_all(
			"Singles",
			filters={"doctype": "Event Booking Settings"},
			fields=["field", "value"],
		)
	}

	# Fields that carry over directly to the new per-company record
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

	companies = frappe.get_all("Company", pluck="name", limit_page_length=0)

	for company in companies:
		if frappe.db.exists("Event Booking Settings", company):
			continue

		doc_data = {"doctype": "Event Booking Settings", "company": company}

		# Apply migrated values from the old single record
		for field in carried_fields:
			if field in old_values:
				doc_data[field] = old_values[field]

		try:
			frappe.get_doc(doc_data).insert(ignore_permissions=True)
		except (frappe.DuplicateEntryError, frappe.ValidationError):
			frappe.log_error(
				title=f"migrate_settings_to_per_company: failed for {company}"
			)

	# Clean up the now-redundant Singles rows so there's no stale data
	if old_values:
		frappe.db.delete("Singles", {"doctype": "Event Booking Settings"})

	frappe.db.commit()
