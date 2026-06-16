"""
Patch: rename_event_settings_doctype
Renames the old 'Event Settings' Single DocType to 'Event Booking Settings'.
Migrates existing tabSingles configuration values to the new name.
Safe to re-run — all operations are guarded by existence checks.
"""
import frappe


def execute():
	old_name = "Event Settings"
	new_name = "Event Booking Settings"

	if not frappe.db.exists("DocType", old_name):
		return

	# Guard against colliding with other apps' "Event Settings" DocType
	module = frappe.db.get_value("DocType", old_name, "module")
	if module and module not in ("Event Bookings", "Event Booking"):
		return

	if not frappe.db.exists("DocType", new_name):
		frappe.rename_doc("DocType", old_name, new_name, force=True, ignore_permissions=True)
		frappe.db.commit()
		return

	# Both exist — migrate Singles data from old to new, then delete the old DocType record
	old_values = frappe.db.get_all(
		"Singles",
		filters={"doctype": old_name},
		fields=["field", "value"],
	)

	for row in old_values:
		existing = frappe.db.get_value(
			"Singles", {"doctype": new_name, "field": row.field}, "value"
		)
		if not existing:
			frappe.db.set_value("Singles", {"doctype": new_name, "field": row.field}, "value", row.value)

	# Delete old Singles rows and old DocType record
	frappe.db.delete("Singles", {"doctype": old_name})
	frappe.delete_doc("DocType", old_name, force=True, ignore_permissions=True)
	frappe.db.commit()
