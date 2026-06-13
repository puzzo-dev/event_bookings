import frappe


def execute():
    """Seed default event types if they don't exist."""
    default_types = ["Wedding", "Corporate", "Birthday", "Conference", "Private Party"]
    for t in default_types:
        if not frappe.db.exists("Event Type", t):
            frappe.get_doc({"doctype": "Event Type", "type_name": t}).insert(
                ignore_permissions=True
            )
    frappe.db.commit()
