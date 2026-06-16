import frappe
from frappe import _
from frappe.utils import cstr


def execute(filters=None):
    if not filters:
        filters = {}

    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"fieldname": "event_name", "label": _("Event Booking"), "fieldtype": "Link", "options": "Event Booking", "width": 180},
        {"fieldname": "customer", "label": _("Customer"), "fieldtype": "Link", "options": "Customer", "width": 150},
        {"fieldname": "event_timing", "label": _("Event Timing"), "fieldtype": "Datetime", "width": 150},
        {"fieldname": "booking_status", "label": _("Status"), "fieldtype": "Data", "width": 120},
        {"fieldname": "total_estimated", "label": _("Estimated Revenue"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "total_actual", "label": _("Actual Revenue"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "cogs", "label": _("COGS"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "net_profit", "label": _("Net Profit"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "margin_pct", "label": _("Margin %"), "fieldtype": "Float", "width": 100},
    ]


def get_data(filters):
    cache_key = _cache_key(filters)
    cached = frappe.cache().get(cache_key)
    if cached is not None:
        return cached

    conditions = {}
    if filters.get("from_date"):
        conditions["event_timing"] = [">=", f"{filters['from_date']} 00:00:00"]
    if filters.get("to_date"):
        conditions["event_timing"] = ["<=", f"{filters['to_date']} 23:59:59"]
    if filters.get("customer"):
        conditions["customer"] = filters["customer"]
    if filters.get("event_type"):
        conditions["event_type"] = filters["event_type"]
    if filters.get("booking_status"):
        conditions["booking_status"] = filters["booking_status"]

    bookings = frappe.get_all(
        "Event Booking",
        filters=conditions,
        fields=[
            "name as event_name", "customer", "event_timing", "booking_status",
            "total_estimated", "total_actual"
        ],
        order_by="event_timing desc",
        limit_page_length=0
    )

    if not bookings:
        return []

    # Bulk fetch COGS
    event_names = [eb.event_name for eb in bookings]
    cogs_map = {}
    if event_names:
        cogs_data = frappe.db.sql(
            """
            SELECT se.event_booking, SUM(sed.basic_amount)
            FROM `tabStock Entry Detail` sed
            INNER JOIN `tabStock Entry` se ON se.name = sed.parent
            WHERE se.event_booking IN %s
              AND se.stock_entry_type = 'Material Issue'
              AND se.docstatus = 1
            GROUP BY se.event_booking
            """,
            (tuple(event_names),),
            as_dict=0
        )
        cogs_map = {row[0]: (row[1] or 0) for row in cogs_data}

    data = []
    for eb in bookings:
        revenue = eb.total_actual if eb.total_actual else eb.total_estimated
        revenue = revenue or 0
        cogs = cogs_map.get(eb.event_name, 0)

        net_profit = revenue - cogs
        margin_pct = (net_profit / revenue * 100) if revenue > 0 else 0

        eb.update({
            "net_profit": net_profit,
            "margin_pct": margin_pct,
            "cogs": cogs,
        })
        data.append(eb)

    frappe.cache().set(cache_key, data, expires_in_sec=300)
    return data


def _cache_key(filters):
    """Build a cache key from report filters."""
    if not filters:
        return "event_booking_profitability:no_filters"
    parts = [f"{k}={v}" for k, v in sorted(filters.items()) if v]
    return "event_booking_profitability:" + ",".join(parts)
