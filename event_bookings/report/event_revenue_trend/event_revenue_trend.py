import frappe
from frappe import _


def execute(filters=None):
    if "erpnext" not in frappe.get_installed_apps():
        frappe.throw(_("Event Revenue Trend requires ERPNext to be installed."))
    if not filters:
        filters = {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"fieldname": "period", "label": _("Month"), "fieldtype": "Data", "width": 120},
        {"fieldname": "event_count", "label": _("Events"), "fieldtype": "Int", "width": 100},
        {"fieldname": "confirmed_count", "label": _("Confirmed+"), "fieldtype": "Int", "width": 120},
        {"fieldname": "total_estimated", "label": _("Estimated Revenue"), "fieldtype": "Currency", "width": 160},
        {"fieldname": "total_actual", "label": _("Actual Revenue"), "fieldtype": "Currency", "width": 160},
        {"fieldname": "delta", "label": _("Actual vs Estimated"), "fieldtype": "Currency", "width": 160},
    ]


def get_data(filters):
    # Use positional %s throughout — cannot mix named %(key)s and positional %s
    # in a single frappe.db.sql call.
    conditions = []
    where_values = []

    if filters.get("from_date"):
        conditions.append("event_date >= %s")
        where_values.append(filters["from_date"])
    if filters.get("to_date"):
        conditions.append("event_date <= %s")
        where_values.append(filters["to_date"])

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # confirmed_statuses are hardcoded — parameterised to guard against future edits
    # that might accidentally introduce user-controlled values into the IN list.
    confirmed_statuses = ("Confirmed", "In Preparation", "Executed", "Invoiced", "Paid")
    confirmed_placeholders = ", ".join(["%s"] * len(confirmed_statuses))

    # Parameter order matches SQL appearance: CASE WHEN IN (...) first, WHERE conditions after.
    rows = frappe.db.sql(
        f"""
        SELECT
            DATE_FORMAT(event_date, '%%Y-%%m') AS period,
            COUNT(*) AS event_count,
            SUM(CASE WHEN booking_status IN ({confirmed_placeholders}) THEN 1 ELSE 0 END) AS confirmed_count,
            SUM(total_estimated) AS total_estimated,
            SUM(total_actual) AS total_actual
        FROM `tabEvent Booking`
        {where}
        GROUP BY period
        ORDER BY period ASC
        """,
        (*confirmed_statuses, *where_values),
        as_dict=True,
    )

    for row in rows:
        row["delta"] = (row.total_actual or 0) - (row.total_estimated or 0)

    return rows
