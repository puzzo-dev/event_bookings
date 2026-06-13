import frappe


@frappe.whitelist()
def get_customer_bookings(limit_start=0, limit_page_length=20):
	"""Return event bookings for the logged-in customer portal user."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Please log in to view your bookings.", frappe.AuthenticationError)

	customer = _get_customer_for_user(user)
	if not customer:
		return []

	limit_start = int(limit_start)
	limit_page_length = min(int(limit_page_length), 100)

	return frappe.get_all(
		"Event Booking",
		filters={"customer": customer},
		fields=[
			"name",
			"event_name",
			"booking_status",
			"event_date",
			"event_location",
			"total_estimated",
			"total_actual",
			"quotation",
			"sales_order",
		],
		order_by="event_date desc",
		start=limit_start,
		limit_page_length=limit_page_length,
	)


@frappe.whitelist()
def approve_quotation(event_booking):
	"""Customer approves a quoted event booking."""
	user = frappe.session.user
	if user == "Guest":
		frappe.throw("Please log in.", frappe.AuthenticationError)

	customer = _get_customer_for_user(user)
	if not customer:
		frappe.throw("No customer account linked to your login.")

	doc = frappe.get_doc("Event Booking", event_booking)
	if doc.customer != customer:
		frappe.throw("You do not have permission to approve this booking.", frappe.PermissionError)

	if doc.booking_status != "Quoted":
		frappe.throw("This booking is not in Quoted status.")

	frappe.utils.apply_workflow(doc, "Confirm")
	return {"status": "success", "message": "Booking confirmed successfully."}


def has_website_permission(doc, ptype, user, verbose=False):
	"""Check if the portal user can access this Event Booking."""
	if not user or user == "Guest":
		return False
	customer = _get_customer_for_user(user)
	return customer and doc.customer == customer


def _get_customer_for_user(user):
	"""Look up Customer linked to the portal user via Contact."""
	contact = frappe.db.get_value("Contact", {"user": user}, "name")
	if not contact:
		return None

	links = frappe.get_all(
		"Dynamic Link",
		filters={"parent": contact, "link_doctype": "Customer"},
		fields=["link_name"],
		limit=1,
	)
	return links[0].link_name if links else None
