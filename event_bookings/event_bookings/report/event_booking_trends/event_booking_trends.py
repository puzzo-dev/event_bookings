import frappe
from frappe import _
from frappe.utils import getdate, add_months, add_days, nowdate, get_first_day, get_last_day


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	columns = get_columns(filters)
	data = get_data(filters)
	chart = get_chart_data(filters, columns, data)

	return columns, data, None, chart


def validate_filters(filters):
	if not filters.get("period"):
		filters["period"] = "Monthly"
	if not filters.get("based_on"):
		filters["based_on"] = "Revenue"
	if not filters.get("date_field"):
		filters["date_field"] = "event_timing"
	if not filters.get("from_date"):
		filters["from_date"] = get_first_day(add_months(nowdate(), -11))
	if not filters.get("to_date"):
		filters["to_date"] = nowdate()
	if not filters.get("company"):
		filters["company"] = frappe.defaults.get_user_default("Company")


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
		from frappe.utils import add_years
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


def get_columns(filters):
	period_list = get_period_list(filters)
	based_on = filters.get("based_on", "Revenue")

	columns = [
		{
			"label": _("Metric"),
			"fieldname": "metric",
			"fieldtype": "Data",
			"width": 140,
		}
	]

	for p in period_list:
		columns.append({
			"label": p["label"],
			"fieldname": "period_" + p["label"].replace(" ", "_"),
			"fieldtype": "Currency" if based_on == "Revenue" else "Int",
			"width": 120,
		})

	columns.append({
		"label": _("Total"),
		"fieldname": "total",
		"fieldtype": "Currency" if based_on == "Revenue" else "Int",
		"width": 120,
	})

	return columns


def get_data(filters):
	period_list = get_period_list(filters)
	based_on = filters.get("based_on", "Revenue")
	date_field = get_date_field(filters.get("date_field", "event_timing"))

	company = filters.get("company")
	metric_label = _("Total Revenue") if based_on == "Revenue" else _("Total Count")
	row = {"metric": metric_label}
	total = 0

	for p in period_list:
		key = "period_" + p["label"].replace(" ", "_")
		value = get_period_value(
			based_on=based_on,
			date_field=date_field,
			from_date=p["from_date"],
			to_date=p["to_date"],
			company=company
		)
		row[key] = value
		total += value or 0

	row["total"] = total
	return [row]


def get_period_value(based_on, date_field, from_date, to_date, company):
	conditions = ""
	values = [f"{from_date} 00:00:00", f"{to_date} 23:59:59"]
	
	if company:
		conditions += " AND company = %s"
		values.append(company)

	if based_on == "Revenue":
		result = frappe.db.sql(
			f"""
			SELECT SUM(IF(IFNULL(total_actual, 0) > 0, total_actual, IFNULL(total_estimated, 0)))
			FROM `tabEvent Booking`
			WHERE docstatus < 2
			  AND {date_field} >= %s AND {date_field} <= %s
			  {conditions}
			""",
			tuple(values),
		)
	else:
		result = frappe.db.sql(
			f"""
			SELECT COUNT(name)
			FROM `tabEvent Booking`
			WHERE docstatus < 2
			  AND {date_field} >= %s AND {date_field} <= %s
			  {conditions}
			""",
			tuple(values),
		)

	return (result[0][0] or 0) if result else 0


def get_date_field(field_key):
	mapping = {
		"event_timing": "event_timing",
		"booking_date": "booking_date",
		"event_date": "event_date",
	}
	return mapping.get(field_key, "event_timing")


def get_chart_data(filters, columns, data):
	if not data:
		return None

	period_list = get_period_list(filters)
	labels = [p["label"] for p in period_list]

	datasets = []
	for row in data:
		values = [
			row.get("period_" + p["label"].replace(" ", "_"), 0) or 0
			for p in period_list
		]
		datasets.append({"name": row["metric"], "values": values})

	# Skip chart rendering when there is no data to avoid SVG errors
	all_zero = all(v == 0 for ds in datasets for v in ds["values"])
	if all_zero:
		return None

	based_on = filters.get("based_on", "Revenue")

	return {
		"data": {"labels": labels, "datasets": datasets},
		"type": "line",
		"colors": ["#48BB78"] if based_on == "Revenue" else ["#449CF0"],
		"fieldtype": "Currency" if based_on == "Revenue" else "Int",
		"lineOptions": {"regionFill": 1},
	}

