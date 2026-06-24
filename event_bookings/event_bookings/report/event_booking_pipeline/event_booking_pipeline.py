import frappe
from frappe import _
from event_bookings.utils.helpers import erpnext_installed


def execute(filters=None):
    if not filters:
        filters = {}

    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    cols = [
        {"fieldname": "event_name", "label": _("Event Booking"), "fieldtype": "Link", "options": "Event Booking", "width": 180},
        {"fieldname": "party_name", "label": _("Party"), "fieldtype": "Data", "width": 150},
        {"fieldname": "event_type", "label": _("Event Type"), "fieldtype": "Link", "options": "Event Type", "width": 120},
        {"fieldname": "event_date", "label": _("Event Date"), "fieldtype": "Date", "width": 120},
        {"fieldname": "booking_status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "days_until_event", "label": _("Days Until"), "fieldtype": "Int", "width": 100},
        {"fieldname": "staff_required", "label": _("Staff Required"), "fieldtype": "Int", "width": 120},
        {"fieldname": "staff_assigned", "label": _("Staff Assigned"), "fieldtype": "Int", "width": 120},
    ]
    if erpnext_installed():
        cols += [
            {"fieldname": "total_estimated", "label": _("Est. Revenue"), "fieldtype": "Currency", "width": 140},
            {"fieldname": "total_actual", "label": _("Actual Revenue"), "fieldtype": "Currency", "width": 140},
            {"fieldname": "quotation", "label": _("Quotation"), "fieldtype": "Link", "options": "Quotation", "width": 130},
            {"fieldname": "sales_invoice", "label": _("Invoice"), "fieldtype": "Link", "options": "Sales Invoice", "width": 130},
        ]
    return cols


def get_data(filters):
    conditions = {}
    if filters.get("from_date"):
        conditions["event_date"] = [">=", filters["from_date"]]
    if filters.get("to_date"):
        conditions["event_date"] = ["<=", filters["to_date"]]
    if filters.get("party_name"):
        conditions["party_name"] = ["like", f"%{filters['party_name']}%"]
    if filters.get("event_type"):
        conditions["event_type"] = filters["event_type"]
    if filters.get("booking_status"):
        conditions["booking_status"] = filters["booking_status"]

    base_fields = [
        "name as event_name",
        "party_name",
        "event_type",
        "event_date",
        "booking_status",
    ]
    erpnext_fields = [
        "total_estimated",
        "total_actual",
        "quotation",
        "sales_invoice",
    ]

    fields = base_fields + (erpnext_fields if erpnext_installed() else [])

    # frappe.get_list respects user permissions; frappe.get_all would bypass them.
    bookings = frappe.get_list(
        "Event Booking",
        filters=conditions,
        fields=fields,
        order_by="event_date asc",
        limit_page_length=500,
    )

    if not bookings:
        return []

    today = frappe.utils.today()
    event_names = [eb.event_name for eb in bookings]
    staff_counts = _get_staff_counts_batch(event_names)

    data = []
    for eb in bookings:
        days_until = (frappe.utils.getdate(eb.event_date) - frappe.utils.getdate(today)).days if eb.event_date else 0
        counts = staff_counts.get(eb.event_name, (0, 0))

        row = {
            "event_name": eb.event_name,
            "party_name": eb.party_name,
            "event_type": eb.event_type,
            "event_date": eb.event_date,
            "booking_status": eb.booking_status,
            "days_until_event": days_until,
            "staff_required": counts[0],
            "staff_assigned": counts[1],
        }
        if erpnext_installed():
            row.update({
                "total_estimated": eb.total_estimated or 0,
                "total_actual": eb.total_actual or 0,
                "quotation": eb.quotation,
                "sales_invoice": eb.sales_invoice,
            })
        data.append(row)

    return data


def _get_staff_counts_batch(event_names):
    """
    Return {event_name: (qty_required, qty_assigned)} for all events in one query.
    Replaces the previous N+1 pattern (_get_staff_counts called per-event in loop).
    """
    if not event_names:
        return {}
    rows = frappe.db.sql(
        """
        SELECT parent, SUM(qty_required) AS req, SUM(qty_assigned) AS asgn
        FROM `tabEvent Staff Requirement`
        WHERE parent IN %s
        GROUP BY parent
        """,
        [event_names],
        as_dict=True,
    )
    return {r.parent: (r.req or 0, r.asgn or 0) for r in rows}
