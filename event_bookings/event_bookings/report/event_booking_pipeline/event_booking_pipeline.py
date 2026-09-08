import frappe
from frappe import _
from frappe.utils import cstr, flt

# Resolve each Currency column against the row's own company, so a
# multi-company site shows the right symbol (ERPNext report convention).
CURRENCY_OPTIONS = "Company:company:default_currency"


def execute(filters=None):
	if not filters:
		filters = {}

	columns = get_columns()
	data = get_data(filters)
	
	total_est = sum(flt(row.get("total_estimated")) for row in data)
	total_act = sum(flt(row.get("total_actual")) for row in data)
	staff_required = sum(flt(row.get("staff_required")) for row in data)
	staff_assigned = sum(flt(row.get("staff_assigned")) for row in data)
	understaffed = sum(
		1 for row in data if flt(row.get("staff_assigned")) < flt(row.get("staff_required"))
	)

	report_summary = [
		{"value": len(data), "indicator": "Blue", "label": _("Total Events"), "datatype": "Int"},
		{"value": total_est, "indicator": "Green", "label": _("Total Estimated Revenue"), "datatype": "Currency"},
		{"value": total_act, "indicator": "Green", "label": _("Total Actual Revenue"), "datatype": "Currency"},
		{"value": staff_assigned, "indicator": "Blue", "label": _("Staff Assigned"), "datatype": "Int"},
		{"value": staff_required, "indicator": "Blue", "label": _("Staff Required"), "datatype": "Int"},
		{"value": understaffed, "indicator": "Red" if understaffed else "Green",
		 "label": _("Under-staffed Events"), "datatype": "Int"},
	]

	return columns, data, None, None, report_summary


def get_columns():
	return [
		{"fieldname": "event_name", "label": _("Event Booking"), "fieldtype": "Link", "options": "Event Booking", "width": 180},
		{"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 160},
		{"fieldname": "event_type", "label": _("Event Type"), "fieldtype": "Link", "options": "Event Type", "width": 120},
		{"fieldname": "event_date", "label": _("Event Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "event_time", "label": _("Event Time"), "fieldtype": "Time", "width": 90},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		# Data (not Int) deliberately: frappe.desk.query_report.add_total_row sums
		# every Int column with no opt-out, and a total of "days until event"
		# is meaningless. align keeps it right-aligned like a number.
		{"fieldname": "days_until_event", "label": _("Days Until"), "fieldtype": "Data",
		 "align": "right", "width": 100},
		{"fieldname": "total_estimated", "label": _("Est. Revenue"), "fieldtype": "Currency", "options": CURRENCY_OPTIONS, "width": 140},
		{"fieldname": "total_actual", "label": _("Actual Revenue"), "fieldtype": "Currency", "options": CURRENCY_OPTIONS, "width": 140},
		{"fieldname": "staff_required", "label": _("Staff Required"), "fieldtype": "Int", "width": 120},
		{"fieldname": "staff_assigned", "label": _("Staff Assigned"), "fieldtype": "Int", "width": 120},
		{"fieldname": "quotation", "label": _("Quotation"), "fieldtype": "Link", "options": "Quotation", "width": 130},
		{"fieldname": "sales_invoice", "label": _("Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 130},
	]


def get_data(filters):
	# Cancelled bookings never appear, matching how ERPNext reports treat
	# cancelled documents: every one of them pins `docstatus = 1`, which drops
	# cancelled rows entirely rather than filtering them by status
	# (see erpnext sales_order_analysis / sales_register). This app cancels by
	# status as well as by docstatus, so both are excluded. "Cancelled" is
	# therefore not offered in the Status filter — it could never match.
	conditions = {"docstatus": ["!=", 2], "status": ["!=", "Cancelled"]}
	if filters.get("from_date") and filters.get("to_date"):
		conditions["event_date"] = ["between", [filters["from_date"], filters["to_date"]]]
	elif filters.get("from_date"):
		conditions["event_date"] = [">=", filters["from_date"]]
	elif filters.get("to_date"):
		conditions["event_date"] = ["<=", filters["to_date"]]
	if filters.get("customer"):
		conditions["customer"] = filters["customer"]
	if filters.get("company"):
		conditions["company"] = filters["company"]
	if filters.get("event_type"):
		conditions["event_type"] = filters["event_type"]
	if filters.get("status") and filters["status"] != "Cancelled":
		conditions["status"] = filters["status"]

	# get_list (not get_all) so the report honours role permissions and the
	# Event Booking permission_query_conditions (planner/company partitioning).
	bookings = frappe.get_list(
		"Event Booking",
		filters=conditions,
		fields=[
			"name as event_name",
			"customer",
			"company",
			"event_type",
			"event_date",
			"event_time",
			"status",
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
			"customer": eb.customer,
			"company": eb.company,
			"event_type": eb.event_type,
			"event_date": eb.event_date,
			"event_time": eb.event_time,
			"status": eb.status,
			"days_until_event": cstr(days_until),
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
