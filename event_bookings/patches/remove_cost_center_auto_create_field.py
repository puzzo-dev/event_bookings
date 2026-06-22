"""
Patch: remove_cost_center_auto_create_field

Removes the 'is_event_cost_center' custom field from Cost Center that was
created by the now-removed per-event Cost Center auto-creation feature.

Safe to re-run — guarded by an existence check.
"""
import frappe


def execute():
	cf_name = "Cost Center-is_event_cost_center"
	if frappe.db.exists("Custom Field", cf_name):
		frappe.delete_doc("Custom Field", cf_name, ignore_permissions=True)
		frappe.db.commit()
