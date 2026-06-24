import frappe
from frappe import _


def execute(filters=None):
    if not filters:
        filters = {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"fieldname": "event_type", "label": _("Event Type"), "fieldtype": "Link", "options": "Event Type", "width": 160},
        {"fieldname": "booking_status", "label": _("Status"), "fieldtype": "Data", "width": 130},
        {"fieldname": "event_count", "label": _("Events"), "fieldtype": "Int", "width": 100},
        {"fieldname": "total_estimated", "label": _("Total Estimated"), "fieldtype": "Currency", "width": 150},
        {"fieldname": "total_actual", "label": _("Total Actual"), "fieldtype": "Currency", "width": 150},
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
    if filters.get("event_type"):
        conditions.append("event_type = %(event_type)s")
        values["event_type"] = filters["event_type"]
    if filters.get("booking_status"):
        conditions.append("booking_status = %(booking_status)s")
        values["booking_status"] = filters["booking_status"]

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    rows = frappe.db.sql(
        f"""
        SELECT
            COALESCE(event_type, '(No Type)') AS event_type,
            booking_status,
            COUNT(*) AS event_count,
            SUM(total_estimated) AS total_estimated,
            SUM(total_actual) AS total_actual
        FROM `tabEvent Booking`
        {where}
        GROUP BY event_type, booking_status
        ORDER BY event_type, booking_status
        """,
        values,
        as_dict=True,
    )
    return rows
