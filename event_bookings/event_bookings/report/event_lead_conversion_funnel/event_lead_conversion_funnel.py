# Copyright (c) 2026, I-Varse Technologies NG and contributors
# For license information, please see license.txt

"""Pipeline stages per period: Leads -> Quotations -> Orders -> Invoiced.

Scoping is by company — on a multi-company site each company is its own line
of business, so the events company's quotations are the event deals.

The two pre-conversion stages are measured on the Quotation, because a deal
that never converts produces no Event Booking. The two post-conversion
stages keep the ``event_booking`` link: there, it is not a scoping trick but
the definition of the stage — a converted deal has a booking.

Requires ERPNext (Quotation, Sales Order and Sales Invoice are ERPNext).
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

# (label, doctype, date field, extra conditions)
STAGES = [
	(_("Leads Quoted"), "Quotation", "transaction_date", {"quotation_to": "Lead"}),
	(_("Quotations Issued"), "Quotation", "transaction_date", {}),
	(_("Orders Confirmed"), "Sales Order", "transaction_date", {"event_booking_set": True}),
	(_("Invoiced"), "Sales Invoice", "posting_date", {"event_booking_set": True}),
]


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
			"label": _("Stage"),
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

	from_date = period_list[0]["from_date"]
	to_date = period_list[-1]["to_date"]
	company = filters.get("company")

	data = []
	for label, doctype, datefield, extra in STAGES:
		buckets = count_stage(doctype, datefield, extra, from_date, to_date, company, period_list)
		row = {"metric": label}
		total = 0
		for index, p in enumerate(period_list):
			value = buckets.get(index, 0)
			row["period_" + p["label"].replace(" ", "_")] = value
			total += value
		row["total"] = total
		data.append(row)

	return data


def count_stage(doctype, datefield, extra, from_date, to_date, company, period_list):
	"""Grouped count of one stage per datefield within the range."""
	conditions = f"{datefield} >= %(from_date)s AND {datefield} <= %(to_date)s AND company = %(company)s"
	if extra.get("event_booking_set"):
		conditions += " AND event_booking IS NOT NULL AND event_booking != ''"
	if extra.get("quotation_to"):
		conditions += " AND quotation_to = %(quotation_to)s"

	rows = frappe.db.sql(
		f"""
		SELECT {datefield} AS bucket_date, COUNT(name) AS value
		FROM `tab{doctype}`
		WHERE docstatus = 1 AND {conditions}
		GROUP BY bucket_date
		""",
		{
			"from_date": from_date,
			"to_date": to_date,
			"company": company,
			"quotation_to": extra.get("quotation_to"),
		},
		as_dict=True,
	)

	buckets = {}
	for row in rows:
		index = get_period_index(period_list, row.bucket_date)
		if index is None:
			continue
		buckets[index] = buckets.get(index, 0) + (row.value or 0)
	return buckets


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
		"type": "bar",
		"fieldtype": "Int",
	}
