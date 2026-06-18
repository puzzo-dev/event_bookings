# Copyright (c) 2026, puxxo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_months, get_first_day, nowdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	columns = get_columns(filters)
	data = get_data(filters)
	chart = get_chart_data(filters, data)

	return columns, data, None, chart


def validate_filters(filters):
	if not filters.get("from_date"):
		filters["from_date"] = get_first_day(add_months(nowdate(), -11))
	if not filters.get("to_date"):
		filters["to_date"] = nowdate()
	if not filters.get("based_on"):
		filters["based_on"] = "Revenue"


def get_columns(filters):
	based_on = filters.get("based_on", "Revenue")

	columns = [
		{
			"label": _("Event Type"),
			"fieldname": "event_type",
			"fieldtype": "Link",
			"options": "Event Type",
			"width": 140,
		},
		{
			"label": _("Value"),
			"fieldname": "value",
			"fieldtype": "Currency" if based_on == "Revenue" else "Int",
			"width": 120,
		}
	]

	return columns


def get_data(filters):
	based_on = filters.get("based_on", "Revenue")
	company = filters.get("company")
	
	conditions = ""
	values = [f"{filters.from_date} 00:00:00", f"{filters.to_date} 23:59:59"]

	if company:
		conditions += " AND company = %s"
		values.append(company)

	if based_on == "Revenue":
		sql = f"""
			SELECT 
				event_type, 
				SUM(IF(IFNULL(total_actual, 0) > 0, total_actual, IFNULL(total_estimated, 0))) as value
			FROM `tabEvent Booking`
			WHERE docstatus < 2
			  AND event_timing >= %s AND event_timing <= %s
			  {conditions}
			GROUP BY event_type
			ORDER BY value DESC
		"""
	else:
		sql = f"""
			SELECT 
				event_type, 
				COUNT(name) as value
			FROM `tabEvent Booking`
			WHERE docstatus < 2
			  AND event_timing >= %s AND event_timing <= %s
			  {conditions}
			GROUP BY event_type
			ORDER BY value DESC
		"""

	result = frappe.db.sql(sql, tuple(values), as_dict=1)
	return result


def get_chart_data(filters, data):
	if not data:
		return None

	labels = []
	values = []

	for row in data:
		labels.append(row.get("event_type") or "Unknown")
		values.append(row.get("value") or 0)

	return {
		"data": {"labels": labels, "datasets": [{"name": filters.get("based_on", "Revenue"), "values": values}]},
		"type": "donut",
		"fieldtype": "Currency" if filters.get("based_on") == "Revenue" else "Int",
	}
