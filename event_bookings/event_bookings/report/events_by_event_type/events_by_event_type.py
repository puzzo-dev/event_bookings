# Copyright (c) 2026, puxxo and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_months, get_first_day, nowdate

from erpnext.accounts.utils import get_fiscal_year


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	columns = get_columns(filters)
	data = get_data(filters)
	chart = get_chart_data(filters, data)

	return columns, data, None, chart


def validate_filters(filters):
	if not filters.get("based_on"):
		filters["based_on"] = "Revenue"

	# Derive date range from fiscal year (same pattern as ERPNext trends)
	if not filters.get("fiscal_year"):
		filters["fiscal_year"] = get_fiscal_year(nowdate())[0]

	# get_fiscal_year(fiscal_year=...) returns (name, start_date, end_date)
	fy_info = get_fiscal_year(fiscal_year=filters["fiscal_year"])
	filters["from_date"] = fy_info[1]
	filters["to_date"] = fy_info[2]


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
	values = [filters.from_date, filters.to_date]

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
			  AND booking_date >= %s AND booking_date <= %s
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
			  AND booking_date >= %s AND booking_date <= %s
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

	# NOTE: do NOT include 'fieldtype' here — frappe's chart_widget.js uses
	# it to build a formatTooltipY formatter that returns HTML
	# (<div style='text-align: right'>…</div>) which the donut legend
	# renders as raw text.
	return {
		"data": {"labels": labels, "datasets": [{"name": filters.get("based_on", "Revenue"), "values": values}]},
		"type": "donut",
	}
