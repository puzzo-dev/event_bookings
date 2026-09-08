import frappe

from event_bookings.permissions import validate_company_filter
from frappe import _
from frappe.utils import getdate, add_months, add_days, add_years, nowdate, get_first_day, get_last_day

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

	period_list = get_period_list(filters)
	columns = get_columns(filters, period_list)
	data = get_data(filters, period_list)
	chart = get_chart_data(filters, period_list, data)

	# Without Group By there is exactly one row, so a total row would just
	# repeat it. Frappe's 6th return value suppresses it in that case.
	skip_total_row = 0 if filters.get("group_by") else 1

	return columns, data, None, chart, None, skip_total_row


def validate_filters(filters):
	if not filters.get("period"):
		filters["period"] = "Monthly"
	if not filters.get("based_on"):
		filters["based_on"] = "Revenue"
	if not filters.get("date_field"):
		filters["date_field"] = "booking_date"
	if not filters.get("company"):
		filters["company"] = frappe.defaults.get_user_default("Company")

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


def get_period_list(filters):
	"""Generate list of period start dates based on from_date, to_date, and period."""
	from_date = getdate(filters.from_date)
	to_date = getdate(filters.to_date)
	period = filters.period

	periods = []
	current = get_first_day(from_date) if period != "Weekly" else from_date

	while current <= to_date:
		period_end = get_period_end(current, period)
		periods.append({
			"label": get_period_label(current, period),
			"from_date": current,
			"to_date": min(period_end, to_date),
		})
		current = add_days(period_end, 1)

	# Safety valve: >24 periods will crash/slow most chart renderers.
	# Keep the most recent 24 so the user sees current data.
	if len(periods) > 24:
		periods = periods[-24:]

	return periods


def get_period_end(start_date, period):
	if period == "Weekly":
		return add_days(start_date, 6)
	elif period == "Monthly":
		return get_last_day(start_date)
	elif period == "Quarterly":
		# Go to end of current quarter
		end = get_last_day(add_months(start_date, 2))
		return end
	elif period == "Yearly":
		return add_days(add_years(get_first_day(start_date), 1), -1)
	return get_last_day(start_date)


def get_period_label(start_date, period):
	if period == "Weekly":
		return "Week " + start_date.strftime("%W %Y")
	elif period == "Monthly":
		return start_date.strftime("%b %Y")
	elif period == "Quarterly":
		quarter = (start_date.month - 1) // 3 + 1
		return f"Q{quarter} {start_date.year}"
	elif period == "Yearly":
		return str(start_date.year)
	return start_date.strftime("%b %Y")


def get_columns(filters, period_list=None):
	if period_list is None:
		period_list = get_period_list(filters)
	based_on = filters.get("based_on", "Revenue")
	group_by = filters.get("group_by")
	value_fieldtype = "Currency" if based_on == "Revenue" else "Int"

	if group_by:
		first_column = {
			"label": _(group_by),
			"fieldname": "metric",
			"fieldtype": "Link",
			"options": group_by,
			"width": 160,
		}
	else:
		first_column = {
			"label": _("Metric"),
			"fieldname": "metric",
			"fieldtype": "Data",
			"width": 140,
		}

	columns = [first_column]

	currency_options = CURRENCY_OPTIONS if value_fieldtype == "Currency" else None

	for p in period_list:
		columns.append({
			"label": p["label"],
			"fieldname": "period_" + p["label"].replace(" ", "_"),
			"fieldtype": value_fieldtype,
			"options": currency_options,
			"width": 120,
		})

	columns.append({
		"label": _("Total"),
		"fieldname": "total",
		"fieldtype": value_fieldtype,
		"options": currency_options,
		"width": 120,
	})

	return columns


def get_data(filters, period_list=None):
	"""One row per series.

	Without ``group_by`` that is a single "Total Revenue" / "Total Count" row.
	With ``group_by`` it is one row per dimension value — the same shape
	ERPNext's Sales Order Trends uses to drive a multi-series trend chart.
	"""
	if period_list is None:
		period_list = get_period_list(filters)
	if not period_list:
		return []

	based_on = filters.get("based_on", "Revenue")
	date_field = get_date_field(filters.get("date_field", "booking_date"))
	group_by = get_group_by_field(filters.get("group_by"))

	rows = get_raw_values(
		based_on=based_on,
		date_field=date_field,
		group_by=group_by,
		from_date=period_list[0]["from_date"],
		to_date=period_list[-1]["to_date"],
		company=filters.get("company"),
	)

	metric_label = _("Total Revenue") if based_on == "Revenue" else _("Total Count")

	series = {}
	for row in rows:
		key = (row.get("series") or _("Not Set")) if group_by else metric_label
		index = get_period_index(period_list, row.get("bucket_date"))
		if index is None:
			continue
		buckets = series.setdefault(key, {})
		buckets[index] = buckets.get(index, 0) + (row.get("value") or 0)

	# Always emit the single row, even with no data, so the report renders.
	if not group_by:
		series.setdefault(metric_label, {})

	company = filters.get("company")
	data = []
	for key, buckets in sorted(series.items(), key=lambda kv: (-sum(kv[1].values()), kv[0])):
		row = {"metric": key, "company": company}
		total = 0
		for index, p in enumerate(period_list):
			value = buckets.get(index, 0)
			row["period_" + p["label"].replace(" ", "_")] = value
			total += value
		row["total"] = total
		data.append(row)

	return data


def get_raw_values(based_on, date_field, group_by, from_date, to_date, company):
	"""Single grouped query over the whole range.

	Replaces the previous one-query-per-period loop, which became
	periods x dimension-values queries once grouping was added.
	"""
	conditions = ""
	values = [f"{from_date} 00:00:00", f"{to_date} 23:59:59"]

	if company:
		conditions += " AND company = %s"
		values.append(company)

	if based_on == "Revenue":
		value_expr = "SUM(IF(IFNULL(total_actual, 0) > 0, total_actual, IFNULL(total_estimated, 0)))"
	else:
		value_expr = "COUNT(name)"

	# date_field and group_by are allowlisted below before reaching SQL.
	series_expr = f"`{group_by}`" if group_by else "NULL"

	return frappe.db.sql(
		f"""
		SELECT
			{series_expr}  AS series,
			{date_field}   AS bucket_date,
			{value_expr}   AS value
		FROM `tabEvent Booking`
		WHERE docstatus < 2
		  AND status != 'Cancelled'
		  AND {date_field} >= %s AND {date_field} <= %s
		  {conditions}
		GROUP BY series, bucket_date
		""",
		tuple(values),
		as_dict=True,
	)


def get_period_index(period_list, value):
	"""Index of the period ``value`` falls in, or None when out of range."""
	if not value:
		return None
	value = getdate(value)
	for index, p in enumerate(period_list):
		if getdate(p["from_date"]) <= value <= getdate(p["to_date"]):
			return index
	return None


# Explicit allowlists — values are interpolated into SQL column positions.
# frappe.throw ensures no unlisted value ever reaches the query.
_SAFE_DATE_FIELDS = frozenset({"booking_date", "event_date"})
_SAFE_GROUP_BY = {"Event Type": "event_type"}


def get_date_field(field_key):
	if field_key not in _SAFE_DATE_FIELDS:
		frappe.throw(_("Invalid date field: {0}").format(field_key))
	return field_key


def get_group_by_field(label):
	"""Map the user-facing Group By label to an allowlisted column, or None."""
	if not label:
		return None
	if label not in _SAFE_GROUP_BY:
		frappe.throw(_("Invalid Group By: {0}").format(label))
	return _SAFE_GROUP_BY[label]


def get_chart_data(filters, period_list, data):
	if not data:
		return None

	labels = [p["label"] for p in period_list]

	datasets = []
	for row in data:
		values = [
			row.get("period_" + p["label"].replace(" ", "_"), 0) or 0
			for p in period_list
		]
		datasets.append({"name": row["metric"], "values": values})

	based_on = filters.get("based_on", "Revenue")

	chart = {
		"data": {"labels": labels, "datasets": datasets},
		"type": "line",
		"fieldtype": "Currency" if based_on == "Revenue" else "Int",
		"lineOptions": {"regionFill": 1},
	}

	# Only pin a colour for the single-series case; a grouped chart needs
	# Frappe's own palette so each series stays distinguishable.
	if len(datasets) == 1:
		chart["colors"] = ["#48BB78"] if based_on == "Revenue" else ["#449CF0"]

	return chart

