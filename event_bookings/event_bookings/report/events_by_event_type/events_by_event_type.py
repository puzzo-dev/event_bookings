# Copyright (c) 2026, puxxo and contributors
# For license information, please see license.txt

import frappe

from event_bookings.permissions import validate_company_filter
from frappe import _
from frappe.utils import nowdate

from event_bookings.utils.erpnext_bridge import get_fiscal_year_safe, get_fiscal_year_dates_safe

# Resolve each Currency column against the row's own company, so a
# multi-company site shows the right symbol (ERPNext report convention).
CURRENCY_OPTIONS = "Company:company:default_currency"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	# Query Reports run raw SQL, so User Permissions do not apply to them.
	# Confine the company filter before any query is built.
	validate_company_filter(filters)
	validate_filters(filters)

	columns = get_columns(filters)
	data = get_data(filters)
	chart = get_chart_data(filters, data)

	return columns, data, None, chart


def validate_filters(filters):
	if not filters.get("based_on"):
		filters["based_on"] = "Revenue"

	# Derive date range from fiscal year
	if not filters.get("fiscal_year"):
		filters["fiscal_year"] = get_fiscal_year_safe()

	start_date, end_date = get_fiscal_year_dates_safe(filters.get("fiscal_year"))
	if start_date and end_date:
		filters["from_date"] = start_date
		filters["to_date"] = end_date
	else:
		# Fallback when no fiscal year is configured (Frappe-only site)
		filters["from_date"] = frappe.utils.get_first_day(nowdate())
		filters["to_date"] = nowdate()


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
			"label": _("Revenue") if based_on == "Revenue" else _("Events"),
			"fieldname": "value",
			"fieldtype": "Currency" if based_on == "Revenue" else "Int",
			"options": CURRENCY_OPTIONS if based_on == "Revenue" else None,
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
			  AND status != 'Cancelled'
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
			  AND status != 'Cancelled'
			  AND booking_date >= %s AND booking_date <= %s
			  {conditions}
			GROUP BY event_type
			ORDER BY value DESC
		"""

	result = frappe.db.sql(sql, tuple(values), as_dict=1)

	# Carry company so the Currency column's link option can resolve, and
	# label bookings with no event type rather than showing a blank row.
	for row in result:
		row["company"] = company
		if not row.get("event_type"):
			row["event_type"] = None

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
