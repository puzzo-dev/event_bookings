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
		frappe.rename_doc("DocType", old_name, new_name, force=True)
		frappe.db.commit()
		return

	# Both exist — migrate Singles data from old to new, then delete the old DocType record
	old_values = frappe.db.sql(
		"SELECT `field`, `value` FROM `tabSingles` WHERE `doctype` = %s",
		old_name,
		as_dict=True,
	)

	for row in old_values:
		existing = frappe.db.sql(
			"SELECT `value` FROM `tabSingles` WHERE `doctype` = %s AND `field` = %s",
			(new_name, row.field),
		)
		if not existing:
			frappe.db.sql(
				"INSERT INTO `tabSingles` (`doctype`, `field`, `value`) VALUES (%s, %s, %s)",
				(new_name, row.field, row.value),
			)

	# Delete old Singles rows and old DocType record
	frappe.db.sql("DELETE FROM `tabSingles` WHERE `doctype` = %s", old_name)
	frappe.delete_doc("DocType", old_name, force=True)
	frappe.db.commit()
