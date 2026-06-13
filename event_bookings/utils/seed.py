import frappe

DEFAULT_EVENT_TYPES = ["Wedding", "Corporate", "Birthday", "Conference", "Private Party"]


def seed_event_types():
	"""Create default Event Type records if none exist."""
	for t in DEFAULT_EVENT_TYPES:
		try:
			if not frappe.db.exists("Event Type", t):
				frappe.get_doc({"doctype": "Event Type", "type_name": t}).insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(title=f"Failed to seed Event Type: {t}")
	frappe.db.commit()
