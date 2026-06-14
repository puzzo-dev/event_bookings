import frappe
from frappe import _


def execute(filters=None):
	if not filters:
		filters = {}

	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{
			"fieldname": "event_name",
			"label": _("Event Booking"),
			"fieldtype": "Link",
			"options": "Event Booking",
			"width": 180,
		},
		{
			"fieldname": "customer",
			"label": _("Customer"),
			"fieldtype": "Link",
			"options": "Customer",
			"width": 150,
		},
		{
			"fieldname": "event_type",
			"label": _("Event Type"),
			"fieldtype": "Link",
			"options": "Event Type",
			"width": 120,
		},
		{"fieldname": "event_date", "label": _("Event Date"), "fieldtype": "Date", "width": 120},
		{"fieldname": "booking_status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "days_until_event", "label": _("Days Until"), "fieldtype": "Int", "width": 100},
		{"fieldname": "total_estimated", "label": _("Est. Revenue"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "total_actual", "label": _("Actual Revenue"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "staff_required", "label": _("Staff Required"), "fieldtype": "Int", "width": 120},
		{"fieldname": "staff_assigned", "label": _("Staff Assigned"), "fieldtype": "Int", "width": 120},
		{
			"fieldname": "quotation",
			"label": _("Quotation"),
			"fieldtype": "Link",
			"options": "Quotation",
			"width": 130,
		},
		{
			"fieldname": "sales_invoice",
			"label": _("Invoice"),
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 130,
		},
	]


def get_data(filters):
	conditions = {}
	if filters.get("from_date"):
		conditions["event_date"] = [">=", filters["from_date"]]
	if filters.get("to_date"):
		conditions["event_date"] = ["<=", filters["to_date"]]
	if filters.get("customer"):
		conditions["customer"] = filters["customer"]
	if filters.get("event_type"):
		conditions["event_type"] = filters["event_type"]
	if filters.get("booking_status"):
		conditions["booking_status"] = filters["booking_status"]

	bookings = frappe.get_all(
		"Event Booking",
		filters=conditions,
		fields=[
			"name as event_name",
			"customer",
			"event_type",
			"event_date",
			"booking_status",
			"total_estimated",
			"total_actual",
			"quotation",
			"sales_invoice",
		],
		order_by="event_date asc",
	)

	today = frappe.utils.today()
	data = []
	for eb in bookings:
		days_until = (
			(frappe.utils.getdate(eb.event_date) - frappe.utils.getdate(today)).days if eb.event_date else 0
		)
		staff_required, staff_assigned = _get_staff_counts(eb.event_name)

		data.append(
			{
				"event_name": eb.event_name,
				"customer": eb.customer,
				"event_type": eb.event_type,
				"event_date": eb.event_date,
				"booking_status": eb.booking_status,
				"days_until_event": days_until,
				"total_estimated": eb.total_estimated or 0,
				"total_actual": eb.total_actual or 0,
				"staff_required": staff_required,
				"staff_assigned": staff_assigned,
				"quotation": eb.quotation,
				"sales_invoice": eb.sales_invoice,
			}
		)

	return data


def _get_staff_counts(event_name):
	"""Return (qty_required, qty_assigned) for an event from staff requirements."""
	rows = frappe.db.sql(
		"""
        SELECT SUM(qty_required), SUM(qty_assigned)
        FROM `tabEvent Staff Requirement`
        WHERE parent = %s
        """,
		event_name,
	)
	if rows and rows[0]:
		return rows[0][0] or 0, rows[0][1] or 0
	return 0, 0
