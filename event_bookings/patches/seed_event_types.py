import frappe


def execute():
	"""Seed default event types if they don't exist."""
	default_types = ["Wedding", "Corporate", "Birthday", "Conference", "Private Party"]
	for t in default_types:
		try:
			if not frappe.db.exists("Event Type", t):
				frappe.get_doc({"doctype": "Event Type", "type_name": t}).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(title=f"Failed to seed Event Type: {t}")
	frappe.db.commit()
