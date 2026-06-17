import frappe
from frappe import _
from frappe.utils import flt


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
        {"fieldname": "damages_cost", "label": _("Damages / Losses"), "fieldtype": "Currency", "width": 120},
        {"fieldname": "net_profit", "label": _("Net Profit"), "fieldtype": "Currency", "width": 140},
        {"fieldname": "margin_pct", "label": _("Margin %"), "fieldtype": "Float", "width": 100},
        {"fieldname": "revenue_type", "label": _("Revenue Basis"), "fieldtype": "Data", "width": 110},
    ]


def _get_cogs_map(event_names):
    """Return a dict mapping event_name → total COGS from submitted Material Issue Stock Entries."""
    if not event_names:
        return {}
    rows = frappe.db.sql(
        """
        SELECT se.event_booking, SUM(sed.basic_amount) AS total
        FROM `tabStock Entry Detail` sed
        INNER JOIN `tabStock Entry` se ON se.name = sed.parent
        WHERE se.event_booking IN %s
          AND se.stock_entry_type = 'Material Issue'
          AND se.docstatus = 1
        GROUP BY se.event_booking
        """,
        (event_names,),
        as_dict=True,
    )
    return {r.event_booking: r.total for r in rows}


def _get_damages_map(event_names):
    """Return a dict mapping event_name → total damages from Stock Reconciliation write-downs."""
    if not event_names:
        return {}
    rows = frappe.db.sql(
        """
        SELECT sr.event_booking,
               SUM((sri.current_qty - sri.qty) * sri.valuation_rate) AS total
        FROM `tabStock Reconciliation Item` sri
        INNER JOIN `tabStock Reconciliation` sr ON sr.name = sri.parent
        WHERE sr.event_booking IN %s
          AND sr.docstatus = 1
          AND sri.current_qty > sri.qty
        GROUP BY sr.event_booking
        """,
        (event_names,),
        as_dict=True,
    )
    return {r.event_booking: flt(r.total) for r in rows}


def get_data(filters):
    conditions = {}
    if filters.get("from_date") and filters.get("to_date"):
        conditions["event_timing"] = ["between", [
            f"{filters['from_date']} 00:00:00",
            f"{filters['to_date']} 23:59:59",
        ]]
    elif filters.get("from_date"):
        conditions["event_timing"] = [">=", f"{filters['from_date']} 00:00:00"]
    elif filters.get("to_date"):
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
        limit_page_length=0,
    )

    event_names = tuple(eb.event_name for eb in bookings)
    cogs_map = _get_cogs_map(event_names)
    damages_map = _get_damages_map(event_names)

    data = []
    for eb in bookings:
        revenue = eb.total_actual if eb.total_actual else eb.total_estimated
        revenue_type = _("Actual") if eb.total_actual else _("Estimated")
        damages = damages_map.get(eb.event_name, 0)
        revenue = revenue or 0
        cogs = cogs_map.get(eb.event_name, 0)

        net_profit = revenue - cogs - damages
        margin_pct = (net_profit / revenue * 100) if revenue > 0 else 0

        eb.update({
            "net_profit": net_profit,
            "margin_pct": margin_pct,
            "cogs": cogs,
            "damages_cost": damages,
            "revenue_type": revenue_type,
        })
        data.append(eb)

    return data
