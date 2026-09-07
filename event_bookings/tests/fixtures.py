import frappe


def _leaf_group(doctype):
    """First non-group node of a tree doctype (Customer Group / Territory).

    ERPNext party validation rejects group-type Customer Group / Territory,
    and sites without a Selling Settings default fall back to the root
    (group) node — so test customers must pin leaf nodes explicitly.
    """
    return frappe.db.get_value(doctype, {"is_group": 0}, "name", order_by="lft asc")


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
                    "customer_group": _leaf_group("Customer Group"),
                    "territory": _leaf_group("Territory"),
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
                "customer_group": _leaf_group("Customer Group"),
                "territory": _leaf_group("Territory"),
            }
        ).insert(ignore_permissions=True)
    return name


def ensure_test_customer_leaf_details(name="Test Event Customer"):
	"""Pin the test Customer to leaf Customer Group / Territory nodes.

	ERPNext party-details resolution (run on Quotation validate) rejects
	group-type Customer Group / Territory, and sites without a default fall
	back to the root (group) node — test customers must be pinned explicitly.
	"""
	if not frappe.db.exists("DocType", "Customer"):
		return
	if not frappe.db.exists("Customer", name):
		get_or_create_test_customer(name)
		return
	customer = frappe.get_doc("Customer", name)
	changed = False
	if not customer.customer_group or frappe.db.get_value(
		"Customer Group", customer.customer_group, "is_group"
	):
		customer.customer_group = frappe.db.get_value(
			"Customer Group", {"is_group": 0}, "name"
		)
		changed = True
	if not customer.territory or frappe.db.get_value(
		"Territory", customer.territory, "is_group"
	):
		customer.territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
		changed = True
	if changed:
		customer.save(ignore_permissions=True)


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
