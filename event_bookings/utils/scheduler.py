import frappe
from frappe.utils import today, add_days, getdate


def daily():
    """Daily scheduled tasks."""
    sync_invoice_payment_status()
    send_pre_event_reminders(days=3)
    send_unstaffed_alerts()


def hourly():
    """Hourly scheduled tasks."""
    pass


def sync_invoice_payment_status():
    """Transition Invoiced → Paid when linked Sales Invoice is paid."""
    events = frappe.get_all(
        "Event Booking",
        filters={"booking_status": "Invoiced", "sales_invoice": ("is", "set")},
        fields=["name", "sales_invoice"],
    )
    for eb in events:
        si_status = frappe.db.get_value("Sales Invoice", eb.sales_invoice, "status")
        if si_status == "Paid":
            doc = frappe.get_doc("Event Booking", eb.name)
            doc.booking_status = "Paid"
            doc.save(ignore_permissions=True)


def send_pre_event_reminders(days=3):
    """Send reminders to staff T-3 and T-1 days before event."""
    target_date = add_days(today(), days)
    events = frappe.get_all(
        "Event Booking",
        filters={
            "event_date": target_date,
            "booking_status": ("in", ["In Preparation", "Confirmed"]),
        },
        fields=["name", "event_name", "event_date"],
    )
    for ev in events:
        # Placeholder for notification logic
        pass


def send_unstaffed_alerts():
    """Alert Event Manager when staff requirements are not met."""
    events = frappe.get_all(
        "Event Booking",
        filters={"booking_status": "In Preparation"},
        fields=["name"],
    )
    for ev in events:
        doc = frappe.get_doc("Event Booking", ev.name)
        for req in doc.staff_requirements:
            if (req.qty_assigned or 0) < req.qty_required:
                # Placeholder for notification logic
                pass
