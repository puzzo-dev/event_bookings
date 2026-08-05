import frappe
from frappe import _
from frappe.utils import getdate, add_months, add_days, add_years, nowdate, get_first_day, get_last_day

from event_bookings.utils.erpnext_bridge import get_fiscal_year_safe, get_fiscal_year_dates_safe


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	period_list = get_period_list(filters)
	columns = get_columns(filters, period_list)
	data = get_data(filters, period_list)
	chart = get_chart_data(filters, period_list, data)

	return columns, data, None, chart


def validate_filters(filters):
	if not filters.get("period"):
		filters["period"] = "Monthly"
	if not filters.get("based_on"):
		filters["based_on"] = "Revenue"
	if not filters.get("group_by"):
		filters["group_by"] = ""
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

	columns = [
		{
			"label": _("Event Type") if filters.get("group_by") == "Event Type" else _("Metric"),
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


def get_data(filters, period_list=None):
	if period_list is None:
		period_list = get_period_list(filters)
	based_on = filters.get("based_on", "Revenue")
	date_field = get_date_field(filters.get("date_field", "booking_date"))
	company = filters.get("company")

	if filters.get("group_by") == "Event Type":
		return _get_data_by_event_type(based_on, date_field, company, period_list)

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


def _get_data_by_event_type(based_on, date_field, company, period_list):
	"""One row per Event Type, so the chart renders a series per type.

	Bookings with no event_type are grouped under "Unassigned" rather than
	dropped, otherwise the series totals silently disagree with the ungrouped
	chart.
	"""
	rows_by_type = {}

	for p in period_list:
		key = "period_" + p["label"].replace(" ", "_")
		for event_type, value in get_period_values_by_event_type(
			based_on=based_on,
			date_field=date_field,
			from_date=p["from_date"],
			to_date=p["to_date"],
			company=company,
		).items():
			row = rows_by_type.setdefault(event_type, {"metric": event_type, "total": 0})
			row[key] = value
			row["total"] += value or 0

	# Zero-fill so every series has a value at every period — a missing key
	# renders as a gap in the line rather than a zero.
	for row in rows_by_type.values():
		for p in period_list:
			row.setdefault("period_" + p["label"].replace(" ", "_"), 0)

	# Largest first: the report table reads best that way.  Chart colour does
	# NOT come from this order — see _event_type_colour.
	return sorted(rows_by_type.values(), key=lambda r: r["total"], reverse=True)


def get_period_values_by_event_type(based_on, date_field, from_date, to_date, company):
	"""Return {event_type: value} for one period — a single grouped query."""
	conditions = ""
	values = [f"{from_date} 00:00:00", f"{to_date} 23:59:59"]

	if company:
		conditions += " AND company = %s"
		values.append(company)

	measure = (
		"SUM(IF(IFNULL(total_actual, 0) > 0, total_actual, IFNULL(total_estimated, 0)))"
		if based_on == "Revenue"
		else "COUNT(name)"
	)

	rows = frappe.db.sql(
		f"""
		SELECT IFNULL(NULLIF(event_type, ''), {frappe.db.escape(_("Unassigned"))}) AS event_type,
		       {measure} AS value
		FROM `tabEvent Booking`
		WHERE docstatus < 2
		  AND {date_field} >= %s AND {date_field} <= %s
		  {conditions}
		GROUP BY event_type
		""",
		tuple(values),
		as_dict=True,
	)
	return {r.event_type: (r.value or 0) for r in rows}


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


# Explicit allowlist — values are used directly in SQL column positions.
# frappe.throw ensures no unlisted value ever reaches the query.
_SAFE_DATE_FIELDS = frozenset({"booking_date", "event_date"})


def get_date_field(field_key):
	if field_key not in _SAFE_DATE_FIELDS:
		frappe.throw(_("Invalid date field: {0}").format(field_key))
	return field_key


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
	grouped = filters.get("group_by") == "Event Type"

	if grouped:
		colors = [_event_type_colour(row["metric"]) for row in data]
	else:
		colors = ["#199e70"] if based_on == "Revenue" else ["#3987e5"]

	return {
		"data": {"labels": labels, "datasets": datasets},
		"type": "line",
		"colors": colors,
		"fieldtype": "Currency" if based_on == "Revenue" else "Int",
		# regionFill only reads well with a single series; with one line per
		# event type the translucent fills stack into mud.
		"lineOptions": {"regionFill": 0 if grouped else 1, "hideDots": 0},
	}


# Categorical palette, validated for BOTH light and dark desk surfaces
# (lightness band, chroma floor, CVD separation, normal-vision floor and 3:1
# contrast all pass in each mode).  Fixed order, never cycled.
_SERIES_COLOURS = (
	"#3987e5",  # blue
	"#d95926",  # orange
	"#199e70",  # aqua
	"#c98500",  # yellow
	"#d55181",  # magenta
	"#008300",  # green
	"#9085e9",  # violet
	"#e66767",  # red
)
_OTHER_COLOUR = "#8d8d86"  # neutral — anything past slot 8


def _event_type_colour(event_type):
	"""Map an Event Type to a fixed palette slot.

	The slot comes from the alphabetical position of the type across ALL Event
	Types, not from its rank in the current result set — so filtering the report
	down to fewer periods (or one type dropping to zero) never repaints the
	series that remain.  Past slot 8 everything shares one neutral, because a
	generated 9th hue would not survive the contrast/CVD checks.
	"""
	order = _all_event_types()
	try:
		idx = order.index(event_type)
	except ValueError:
		return _OTHER_COLOUR
	return _SERIES_COLOURS[idx] if idx < len(_SERIES_COLOURS) else _OTHER_COLOUR


def _all_event_types():
	names = frappe.get_all("Event Type", pluck="name", order_by="name asc")
	names.append(_("Unassigned"))
	return names

