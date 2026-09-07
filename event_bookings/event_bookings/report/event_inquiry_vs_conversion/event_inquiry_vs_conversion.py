# Copyright (c) 2026, I-Varse Technologies NG and contributors
# For license information, please see license.txt

"""Event quotations raised vs won vs lost, per period.

The deal is measured on the Quotation, not the Event Booking. An Event
Booking only exists once a quotation has been accepted, so measuring
conversion from bookings could never see a deal that stopped at quotation —
which is the majority of lost business.

Scoping is by company: on a multi-company site each company is a separate
line of business, so every quotation raised by the events company is an
event deal. Requires ERPNext (Quotation is an ERPNext DocType).
"""

import frappe

from event_bookings.permissions import validate_company_filter
from frappe import _
from frappe.utils import add_days, add_months, add_years, get_first_day, getdate

from event_bookings.utils.erpnext_bridge import (
	get_fiscal_year_dates_safe,
	get_fiscal_year_safe,
	is_erpnext_installed,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	# Query Reports run raw SQL, so User Permissions do not apply to them.
	# Confine the company filter before any query is built.
	validate_company_filter(filters)
	if not is_erpnext_installed():
		frappe.throw(_("This report requires ERPNext to be installed."))

	filters = frappe._dict(filters or {})
	validate_filters(filters)

	period_list = get_period_list(filters)
	columns = get_columns(filters, period_list)
	data = get_data(filters, period_list)
	chart = get_chart_data(filters, period_list, data)

	return columns, data, None, chart, None, 1


def validate_filters(filters):
	if not filters.get("company"):
		filters["company"] = frappe.defaults.get_user_default("Company")
	if not filters.get("period"):
		filters["period"] = "Monthly"
	if not filters.get("fiscal_year"):
		filters["fiscal_year"] = get_fiscal_year_safe()

	start_date, end_date = get_fiscal_year_dates_safe(filters.get("fiscal_year"))
	if start_date and end_date:
		filters["from_date"] = start_date
		filters["to_date"] = end_date
	else:
		# Fallback when no fiscal year is configured (Frappe-only site)
		filters["from_date"] = get_first_day(getdate())
		filters["to_date"] = getdate()


def get_period_list(filters):
	from_date = getdate(filters.from_date)
	to_date = getdate(filters.to_date)
	period = filters.period

	periods = []
	current = get_first_day(from_date)

	while current <= to_date:
		period_end = get_period_end(current, period)
		periods.append(
			{
				"label": get_period_label(current, period),
				"from_date": current,
				"to_date": min(period_end, to_date),
			}
		)
		current = add_days(period_end, 1)

	if len(periods) > 24:
		periods = periods[-24:]

	return periods


def get_period_end(start_date, period):
	if period == "Quarterly":
		return get_last_day_of(add_months(start_date, 2))
	if period == "Yearly":
		return add_days(add_years(get_first_day(start_date), 1), -1)
	return get_last_day_of(start_date)


def get_last_day_of(date):
	import calendar

	last_day = calendar.monthrange(date.year, date.month)[1]
	return getdate(f"{date.year}-{date.month:02d}-{last_day:02d}")


def get_period_label(start_date, period):
	if period == "Quarterly":
		quarter = (start_date.month - 1) // 3 + 1
		return f"Q{quarter} {start_date.year}"
	if period == "Yearly":
		return str(start_date.year)
	return start_date.strftime("%b %Y")


def get_columns(filters, period_list):
	columns = [
		{
			"label": _("Series"),
			"fieldname": "metric",
			"fieldtype": "Data",
			"width": 160,
		}
	]
	for p in period_list:
		columns.append(
			{
				"label": p["label"],
				"fieldname": "period_" + p["label"].replace(" ", "_"),
				"fieldtype": "Int",
				"width": 120,
			}
		)
	columns.append({"label": _("Total"), "fieldname": "total", "fieldtype": "Int", "width": 120})
	return columns


def get_data(filters, period_list):
	if not period_list:
		return []

	rows = frappe.db.sql(
		"""
		SELECT status, transaction_date AS bucket_date, COUNT(name) AS value
		FROM `tabQuotation`
		WHERE docstatus = 1
		  AND transaction_date >= %(from_date)s AND transaction_date <= %(to_date)s
		  AND company = %(company)s
		GROUP BY status, bucket_date
		""",
		{
			"from_date": period_list[0]["from_date"],
			"to_date": period_list[-1]["to_date"],
			"company": filters.get("company"),
		},
		as_dict=True,
	)

	# Map quotation statuses to the three series.
	series_map = {
		_("Inquiries"): lambda r: True,
		_("Won"): lambda r: r.status == "Ordered",
		_("Lost"): lambda r: r.status in ("Lost", "Expired"),
	}

	series = {label: {} for label in series_map}
	for row in rows:
		index = get_period_index(period_list, row.bucket_date)
		if index is None:
			continue
		for label, match in series_map.items():
			if match(row):
				buckets = series[label]
				buckets[index] = buckets.get(index, 0) + (row.value or 0)

	data = []
	for label in series_map:
		row = {"metric": label}
		total = 0
		for index, p in enumerate(period_list):
			value = series[label].get(index, 0)
			row["period_" + p["label"].replace(" ", "_")] = value
			total += value
		row["total"] = total
		data.append(row)

	return data


def get_period_index(period_list, value):
	if not value:
		return None
	value = getdate(value)
	for index, p in enumerate(period_list):
		if getdate(p["from_date"]) <= value <= getdate(p["to_date"]):
			return index
	return None


def get_chart_data(filters, period_list, data):
	if not data:
		return None

	labels = [p["label"] for p in period_list]
	datasets = []
	for row in data:
		values = [row.get("period_" + p["label"].replace(" ", "_"), 0) or 0 for p in period_list]
		datasets.append({"name": row["metric"], "values": values})

	return {
		"data": {"labels": labels, "datasets": datasets},
		"type": "line",
		"fieldtype": "Int",
		"lineOptions": {"regionFill": 1},
	}
