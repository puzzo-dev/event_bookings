import frappe
from frappe import _
from frappe.utils import flt

# Resolve each Currency column against the row's own company, so a
# multi-company site shows the right symbol (ERPNext report convention).
CURRENCY_OPTIONS = "Company:company:default_currency"


def execute(filters=None):
	if not filters:
		filters = {}

	columns = get_columns()
	data = get_data(filters)
	report_summary = get_report_summary(data)
	return columns, data, None, None, report_summary


def get_report_summary(data):
	"""Number tiles above the table.

	Margin is computed on the summed revenue and profit — a true blended
	margin, which the averaged Margin % in the total row cannot express.
	"""
	if not data:
		return []

	revenue = sum(flt(row.get("total_actual") or row.get("total_estimated")) for row in data)
	cogs = sum(flt(row.get("cogs")) for row in data)
	damages = sum(flt(row.get("damages_cost")) for row in data)
	net_profit = sum(flt(row.get("net_profit")) for row in data)
	margin = (net_profit / revenue * 100) if revenue > 0 else 0

	return [
		{"label": _("Events"), "value": len(data), "datatype": "Int", "indicator": "Blue"},
		{"label": _("Total Revenue"), "value": revenue, "datatype": "Currency", "indicator": "Blue"},
		{"label": _("Total COGS"), "value": cogs, "datatype": "Currency", "indicator": "Orange"},
		{"label": _("Damages / Losses"), "value": damages, "datatype": "Currency", "indicator": "Red"},
		{"label": _("Net Profit"), "value": net_profit, "datatype": "Currency",
		 "indicator": "Green" if net_profit >= 0 else "Red"},
		{"label": _("Blended Margin %"), "value": margin, "datatype": "Percent",
		 "indicator": "Green" if margin >= 0 else "Red"},
	]


def get_columns():
	return [
		{"fieldname": "event_name", "label": _("Event Booking"), "fieldtype": "Link", "options": "Event Booking", "width": 180},
		{"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 160},
		{"fieldname": "event_date", "label": _("Event Date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "event_time", "label": _("Event Time"), "fieldtype": "Time", "width": 90},
		{"fieldname": "booking_status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "total_estimated", "label": _("Estimated Revenue"), "fieldtype": "Currency", "options": CURRENCY_OPTIONS, "width": 140},
		{"fieldname": "total_actual", "label": _("Actual Revenue"), "fieldtype": "Currency", "options": CURRENCY_OPTIONS, "width": 140},
		{"fieldname": "cogs", "label": _("COGS"), "fieldtype": "Currency", "options": CURRENCY_OPTIONS, "width": 120},
		{"fieldname": "damages_cost", "label": _("Damages / Losses"), "fieldtype": "Currency", "options": CURRENCY_OPTIONS, "width": 120},
		{"fieldname": "net_profit", "label": _("Net Profit"), "fieldtype": "Currency", "options": CURRENCY_OPTIONS, "width": 140},
		# Percent (not Float) so Frappe's total row averages the margin rather
		# than summing every row's percentage together.
		{"fieldname": "margin_pct", "label": _("Margin %"), "fieldtype": "Percent", "width": 100},
		{"fieldname": "revenue_type", "label": _("Revenue Basis"), "fieldtype": "Data", "width": 110},
	]


def _get_cogs_map(event_names):
	"""Return a dict mapping event_name → total COGS from submitted Material Issue Stock Entries.

	Returns empty dict when ERPNext is not installed (Stock Entry DocType absent).
	"""
	if not event_names:
		return {}
	if not frappe.db.exists("DocType", "Stock Entry"):
		return {}
	rows = frappe.db.sql(
		"""
		SELECT se.event_booking, SUM(sed.basic_amount) AS total
		FROM `tabStock Entry Detail` sed
		INNER JOIN `tabStock Entry` se ON se.name = sed.parent
		WHERE se.event_booking IN %s
		  AND se.stock_entry_type = 'Material Issue'
		  AND se.docstatus = 1
		GROUP BY se.event_booking
		""",
		(event_names,),
		as_dict=True,
	)
	return {r.event_booking: r.total for r in rows}


def _get_damages_map(event_names):
	"""Return a dict mapping event_name → total damages from Stock Reconciliation write-downs.

	Returns empty dict when ERPNext is not installed (Stock Reconciliation DocType absent).
	"""
	if not event_names:
		return {}
	if not frappe.db.exists("DocType", "Stock Reconciliation"):
		return {}
	rows = frappe.db.sql(
		"""
		SELECT sr.event_booking,
			   SUM((sri.current_qty - sri.qty) * sri.valuation_rate) AS total
		FROM `tabStock Reconciliation Item` sri
		INNER JOIN `tabStock Reconciliation` sr ON sr.name = sri.parent
		WHERE sr.event_booking IN %s
		  AND sr.docstatus = 1
		  AND sri.current_qty > sri.qty
		GROUP BY sr.event_booking
		""",
		(event_names,),
		as_dict=True,
	)
	return {r.event_booking: flt(r.total) for r in rows}


def get_data(filters):
	# Cancelled bookings never appear, matching how ERPNext reports treat
	# cancelled documents: every one of them pins `docstatus = 1`, which drops
	# cancelled rows entirely rather than filtering them by status
	# (see erpnext sales_order_analysis / sales_register). This app cancels by
	# status as well as by docstatus, so both are excluded. "Cancelled" is
	# therefore not offered in the Status filter — it could never match.
	conditions = {"docstatus": ["!=", 2], "booking_status": ["!=", "Cancelled"]}
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
	if filters.get("booking_status") and filters["booking_status"] != "Cancelled":
		conditions["booking_status"] = filters["booking_status"]

	# get_list (not get_all) so the report honours role permissions and the
	# Event Booking permission_query_conditions (planner/company partitioning).
	bookings = frappe.get_list(
		"Event Booking",
		filters=conditions,
		fields=[
			"name as event_name", "customer", "company", "event_date", "event_time",
			"booking_status", "total_estimated", "total_actual"
		],
		order_by="event_date desc, event_time desc",
		limit_page_length=0,
	)

	event_names = tuple(eb.event_name for eb in bookings)
	cogs_map = _get_cogs_map(event_names)
	damages_map = _get_damages_map(event_names)

	data = []
	for eb in bookings:
		revenue = eb.total_actual if eb.total_actual else eb.total_estimated
		revenue_type = _("Actual") if eb.total_actual else _("Estimated")
		damages = damages_map.get(eb.event_name, 0)
		revenue = revenue or 0
		cogs = cogs_map.get(eb.event_name, 0)

		net_profit = revenue - cogs - damages
		margin_pct = (net_profit / revenue * 100) if revenue > 0 else 0

		eb.update({
			"net_profit": net_profit,
			"margin_pct": margin_pct,
			"cogs": cogs,
			"damages_cost": damages,
			"revenue_type": revenue_type,
		})
		data.append(eb)

	return data
