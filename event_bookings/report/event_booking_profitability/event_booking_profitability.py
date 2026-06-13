import frappe


def execute(filters=None):
    if not filters:
        filters = {}

    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"fieldname": "event_name", "label": "Event Booking", "fieldtype": "Link", "options": "Event Booking", "width": 180},
        {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer", "width": 150},
        {"fieldname": "event_date", "label": "Event Date", "fieldtype": "Date", "width": 120},
        {"fieldname": "booking_status", "label": "Status", "fieldtype": "Data", "width": 120},
        {"fieldname": "total_estimated", "label": "Estimated Revenue", "fieldtype": "Currency", "width": 140},
        {"fieldname": "total_actual", "label": "Actual Revenue", "fieldtype": "Currency", "width": 140},
        {"fieldname": "cogs", "label": "COGS", "fieldtype": "Currency", "width": 120},
        {"fieldname": "damages_cost", "label": "Damages / Losses", "fieldtype": "Currency", "width": 120},
        {"fieldname": "net_profit", "label": "Net Profit", "fieldtype": "Currency", "width": 140},
        {"fieldname": "margin_pct", "label": "Margin %", "fieldtype": "Float", "width": 100},
    ]


def get_data(filters):
    conditions = {}
    if filters.get("from_date"):
        conditions["event_date"] = [">=", filters["from_date"]]
    if filters.get("to_date"):
        conditions["event_date"] = ["<=", filters["to_date"]]
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
            "name as event_name", "customer", "event_date", "booking_status",
            "total_estimated", "total_actual", "damages_cost"
        ],
        order_by="event_date desc"
    )

    data = []
    for eb in bookings:
        revenue = eb.total_actual if eb.total_actual else eb.total_estimated
        damages = eb.damages_cost or 0
        revenue = revenue or 0
        
        net_profit = revenue - damages
        margin_pct = (net_profit / revenue * 100) if revenue > 0 else 0
        
        eb.update({
            "net_profit": net_profit,
            "margin_pct": margin_pct,
            "cogs": 0
        })
        data.append(eb)

    return data
