import frappe


def get_or_create_test_customer(name="Test Event Customer"):
	"""Return a test Customer, creating it if needed."""
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
