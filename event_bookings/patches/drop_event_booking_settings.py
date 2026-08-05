"""Remove the Event Booking Settings DocType and every trace of it.

The Single held ten fields and not one was read by any code path:

  * ``pre_event_reminder_days`` / ``enable_whatsapp`` duplicated what Frappe's
    Notification and frappe_whatsapp's WhatsApp Notification already do
    per-doctype, and caused every booking to be reminded twice.
  * ``require_review`` was never referenced by any logic at all.
  * the warehouse / account defaults were read by nothing — only by JS link
    filters on a ``company`` field the DocType never had.

Notifications are now configured per-doctype from the Desk, so the app has no
settings surface. This patch clears the stored values, drops the legacy
per-company tables from the abandoned multi-company design, and deletes the
DocType itself.

Idempotent — safe to re-run. Supersedes the old rename_event_settings_doctype,
make_settings_single and migrate_settings_to_per_company patches.
"""

import frappe

LEGACY_NAMES = ("Event Booking Settings", "Event Settings")


def execute():
	for name in LEGACY_NAMES:
		# Single values live in tabSingles, not in a per-doctype table.
		frappe.db.delete("Singles", {"doctype": name})

		# The abandoned per-company design created a real table; drop it if the
		# site ever ran that migration.
		table = f"tab{name}"
		if frappe.db.table_exists(table):
			frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `{table}`")

		if frappe.db.exists("DocType", name):
			try:
				frappe.delete_doc("DocType", name, force=True, ignore_permissions=True)
				frappe.logger().info(f"event_bookings: removed DocType '{name}'")
			except Exception:
				# Never abort a migrate over cleanup of an already-orphaned DocType.
				frappe.log_error(title=f"event_bookings: could not delete DocType '{name}'")

	# Workspace shortcut and onboarding step are shipped in code and disappear
	# with this release, but existing sites keep their DB rows.
	frappe.db.delete("Workspace Shortcut", {"link_to": ("in", LEGACY_NAMES)})
	for name in ("Configure Event Booking Settings", "Configure Event Settings"):
		if frappe.db.exists("Onboarding Step", name):
			frappe.delete_doc("Onboarding Step", name, force=True, ignore_permissions=True)
