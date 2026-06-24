import frappe
from frappe import _


def execute(filters=None):
    _require_erpnext_and_hrms()
    if not filters:
        filters = {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def _require_erpnext_and_hrms():
    installed = frappe.get_installed_apps()
    if "erpnext" not in installed or "hrms" not in installed:
        frappe.throw(
            _("Event Revenue Trend requires ERPNext and HRMS to be installed.")
        )


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
    conditions = []
    values = {}

    if filters.get("from_date"):
        conditions.append("event_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("event_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    confirmed_statuses = ("Confirmed", "In Preparation", "Executed", "Invoiced", "Paid")
    confirmed_list = ", ".join(f"'{s}'" for s in confirmed_statuses)

    rows = frappe.db.sql(
        f"""
        SELECT
            DATE_FORMAT(event_date, '%%Y-%%m') AS period,
            COUNT(*) AS event_count,
            SUM(CASE WHEN booking_status IN ({confirmed_list}) THEN 1 ELSE 0 END) AS confirmed_count,
            SUM(total_estimated) AS total_estimated,
            SUM(total_actual) AS total_actual
        FROM `tabEvent Booking`
        {where}
        GROUP BY period
        ORDER BY period ASC
        """,
        values,
        as_dict=True,
    )

    for row in rows:
        row["delta"] = (row.total_actual or 0) - (row.total_estimated or 0)

    return rows
