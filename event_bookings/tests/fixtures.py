import frappe


def get_or_create_test_party():
    """
    Return (party_type, party_name) for use in Event Booking test fixtures.

    When ERPNext is installed, creates a Customer record and returns
    ("Customer", name).  On standalone Frappe, returns ("Individual", name)
    with no external DocType creation needed.
    """
    if "erpnext" in frappe.get_installed_apps():
        name = "Test Event Customer"
        if not frappe.db.exists("Customer", name):
            frappe.get_doc(
                {
                    "doctype": "Customer",
                    "customer_name": name,
                    "customer_type": "Individual",
                }
            ).insert(ignore_permissions=True)
        return "Customer", name
    else:
        return "Individual", "Test Event Individual"


def get_or_create_test_customer(name="Test Event Customer"):
    """Return a Customer name, creating the record if needed.

    Only meaningful when ERPNext is installed. Tests that call this function
    should be skipped on plain-Frappe sites via skipUnless or a conditional.
    """
    if not frappe.db.exists("DocType", "Customer"):
        frappe.throw("ERPNext is required for customer-based tests.")
    if not frappe.db.exists("Customer", name):
        frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": name,
                "customer_type": "Individual",
            }
        ).insert(ignore_permissions=True)
    return name


def get_or_create_test_event_type(name="Test Event"):
    """Return a test Event Type, creating it if needed."""
    if not frappe.db.exists("Event Type", name):
        frappe.get_doc({"doctype": "Event Type", "type_name": name}).insert(ignore_permissions=True)
    return name


def get_or_create_test_item(item_code):
    """Return a test Item, creating it if needed."""
    if not frappe.db.exists("Item", item_code):
        item = frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": item_code,
                "item_name": item_code,
                "item_group": "Services",
                "stock_uom": "Nos",
                "is_stock_item": 0,
                "standard_rate": 500,
            }
        )
        item.insert(ignore_permissions=True, set_name=item_code)
    return item_code
