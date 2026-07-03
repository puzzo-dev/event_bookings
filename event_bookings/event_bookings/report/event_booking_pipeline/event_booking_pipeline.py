import frappe
from frappe import _


def execute(filters=None):
	if not filters:
		filters = {}

	columns = get_columns()
	data = get_data(filters)
	
	total_est = sum(row.get("total_estimated", 0) for row in data)
	total_act = sum(row.get("total_actual", 0) for row in data)
	
	report_summary = [
		{"value": len(data), "indicator": "Blue", "label": _("Total Events"), "datatype": "Int"},
		{"value": total_est, "indicator": "Green", "label": _("Total Estimated Revenue"), "datatype": "Currency"},
		{"value": total_act, "indicator": "Green", "label": _("Total Actual Revenue"), "datatype": "Currency"},
	]
	
	return columns, data, None, None, report_summary


def get_columns():
	return [
		{"fieldname": "event_name", "label": _("Event Booking"), "fieldtype": "Link", "options": "Event Booking", "width": 180},
		{"fieldname": "party_type", "label": _("Party Type"), "fieldtype": "Data", "width": 100},
		{"fieldname": "party_name", "label": _("Party"), "fieldtype": "Dynamic Link", "options": "party_type", "width": 160},
		{"fieldname": "event_type", "label": _("Event Type"), "fieldtype": "Link", "options": "Event Type", "width": 120},
		{"fieldname": "event_date", "label": _("Event Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "event_time", "label": _("Event Time"), "fieldtype": "Time", "width": 90},
		{"fieldname": "booking_status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "days_until_event", "label": _("Days Until"), "fieldtype": "Int", "width": 100},
		{"fieldname": "total_estimated", "label": _("Est. Revenue"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "total_actual", "label": _("Actual Revenue"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "staff_required", "label": _("Staff Required"), "fieldtype": "Int", "width": 120},
		{"fieldname": "staff_assigned", "label": _("Staff Assigned"), "fieldtype": "Int", "width": 120},
		{"fieldname": "quotation", "label": _("Quotation"), "fieldtype": "Link", "options": "Quotation", "width": 130},
		{"fieldname": "sales_invoice", "label": _("Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 130},
	]


def get_data(filters):
	conditions = {"docstatus": ["!=", 2]}
	if filters.get("from_date") and filters.get("to_date"):
		conditions["event_date"] = ["between", [filters["from_date"], filters["to_date"]]]
	elif filters.get("from_date"):
		conditions["event_date"] = [">=", filters["from_date"]]
	elif filters.get("to_date"):
		conditions["event_date"] = ["<=", filters["to_date"]]
	if filters.get("party_type"):
		conditions["party_type"] = filters["party_type"]
	if filters.get("party_name"):
		conditions["party_name"] = filters["party_name"]
	if filters.get("company"):
		conditions["company"] = filters["company"]
	if filters.get("event_type"):
		conditions["event_type"] = filters["event_type"]
	if filters.get("booking_status"):
		conditions["booking_status"] = filters["booking_status"]

	# get_list (not get_all) so the report honours role permissions and the
	# Event Booking permission_query_conditions (planner/company partitioning).
	bookings = frappe.get_list(
		"Event Booking",
		filters=conditions,
		fields=[
			"name as event_name",
			"party_type",
			"party_name",
			"event_type",
			"event_date",
			"event_time",
			"booking_status",
			"total_estimated",
			"total_actual",
			"quotation",
			"sales_invoice",
		],
		order_by="event_date asc, event_time asc",
		limit_page_length=0,
	)

	today = frappe.utils.today()
	event_names = tuple(eb.event_name for eb in bookings)
	staff_map = _get_staff_counts_map(event_names)

	data = []
	for eb in bookings:
		days_until = (frappe.utils.getdate(eb.event_date) - frappe.utils.getdate(today)).days if eb.event_date else 0
		staff_required, staff_assigned = staff_map.get(eb.event_name, (0, 0))

		data.append({
			"event_name": eb.event_name,
			"party_type": eb.party_type,
			"party_name": eb.party_name,
			"event_type": eb.event_type,
			"event_date": eb.event_date,
			"event_time": eb.event_time,
			"booking_status": eb.booking_status,
			"days_until_event": days_until,
			"total_estimated": eb.total_estimated or 0,
			"total_actual": eb.total_actual or 0,
			"staff_required": staff_required,
			"staff_assigned": staff_assigned,
			"quotation": eb.quotation,
			"sales_invoice": eb.sales_invoice,
		})

	return data


def _get_staff_counts_map(event_names):
	"""Return a dict mapping event_name → (qty_required, qty_assigned) from staff requirements."""
	if not event_names:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT
			parent,
			SUM(qty_required) AS qty_required,
			SUM(qty_assigned) AS qty_assigned
		FROM `tabEvent Staff Requirement`
		WHERE parent IN %s
		GROUP BY parent
		""",
		(event_names,),
		as_dict=True,
	)
	return {
		r.parent: (r.qty_required or 0, r.qty_assigned or 0)
		for r in rows
	}
