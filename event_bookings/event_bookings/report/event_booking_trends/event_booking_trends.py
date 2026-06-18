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
			"label": _("Event Status"),
			"fieldname": "booking_status",
			"fieldtype": "Data",
			"width": 140,
		}
	]

	for p in period_list:
		if based_on == "Revenue":
			columns.append({
				"label": p["label"],
				"fieldname": "period_" + p["label"].replace(" ", "_"),
				"fieldtype": "Currency",
				"width": 120,
			})
		else:
			columns.append({
				"label": p["label"],
				"fieldname": "period_" + p["label"].replace(" ", "_"),
				"fieldtype": "Int",
				"width": 100,
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
	booking_statuses = get_booking_statuses(filters)

	rows = []

	for status in booking_statuses:
		row = {"booking_status": status}
		total = 0

		for p in period_list:
			key = "period_" + p["label"].replace(" ", "_")
			value = get_period_value(
				status=status,
				based_on=based_on,
				date_field=date_field,
				from_date=p["from_date"],
				to_date=p["to_date"],
				filters=filters,
			)
			row[key] = value
			total += value or 0

		row["total"] = total
		rows.append(row)

	# Add total row
	total_row = {"booking_status": _("Total")}
	grand_total = 0
	for p in period_list:
		key = "period_" + p["label"].replace(" ", "_")
		col_total = sum((r.get(key) or 0) for r in rows)
		total_row[key] = col_total
		grand_total += col_total
	total_row["total"] = grand_total
	rows.append(total_row)

	return rows


def get_booking_statuses(filters):
	"""Return distinct booking_status values in the date range."""
	date_field = get_date_field(filters.get("date_field", "event_timing"))
	conditions = get_base_conditions(filters, date_field)

	statuses = frappe.db.sql(
		f"""
		SELECT DISTINCT booking_status
		FROM `tabEvent Booking`
		WHERE docstatus < 2
		  AND {conditions["date_filter"]}
		ORDER BY booking_status
		""",
		conditions["values"],
		as_list=True,
	)
	result = [s[0] for s in statuses if s[0]]
	return result or ["Draft", "Confirmed", "Completed", "Cancelled"]


def get_period_value(status, based_on, date_field, from_date, to_date, filters):
	if based_on == "Revenue":
		result = frappe.db.sql(
			f"""
			SELECT SUM(IF(IFNULL(total_actual, 0) > 0, total_actual, IFNULL(total_estimated, 0)))
			FROM `tabEvent Booking`
			WHERE docstatus < 2
			  AND booking_status = %s
			  AND {date_field} >= %s AND {date_field} <= %s
			""",
			(status, f"{from_date} 00:00:00", f"{to_date} 23:59:59"),
		)
	else:
		result = frappe.db.sql(
			f"""
			SELECT COUNT(name)
			FROM `tabEvent Booking`
			WHERE docstatus < 2
			  AND booking_status = %s
			  AND {date_field} >= %s AND {date_field} <= %s
			""",
			(status, f"{from_date} 00:00:00", f"{to_date} 23:59:59"),
		)

	return (result[0][0] or 0) if result else 0


def get_base_conditions(filters, date_field):
	from_date = filters.get("from_date", get_first_day(add_months(nowdate(), -11)))
	to_date = filters.get("to_date", nowdate())

	return {
		"date_filter": f"{date_field} >= %s AND {date_field} <= %s",
		"values": (f"{from_date} 00:00:00", f"{to_date} 23:59:59"),
	}


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
		if row.get("booking_status") == _("Total"):
			continue
		values = [
			row.get("period_" + p["label"].replace(" ", "_"), 0) or 0
			for p in period_list
		]
		datasets.append({"name": row["booking_status"], "values": values})

	based_on = filters.get("based_on", "Revenue")

	return {
		"data": {"labels": labels, "datasets": datasets},
		"type": "line",
		"fieldtype": "Currency" if based_on == "Revenue" else "Int",
		"lineOptions": {"regionFill": 1},
		"axisOptions": {"shortenYAxisNumbers": 1},
	}
