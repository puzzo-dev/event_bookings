import frappe
from frappe.utils import add_days, today


def daily():
    """Daily scheduled tasks."""
    for name, task in (
        ("sync_invoice_payment_status", sync_invoice_payment_status),
        ("send_pre_event_reminders_3d", lambda: send_pre_event_reminders(days=3)),
        ("send_pre_event_reminders_1d", lambda: send_pre_event_reminders(days=1)),
        ("send_unstaffed_alerts", send_unstaffed_alerts),
    ):
        try:
            task()
        except Exception:
            frappe.log_error(
                title=f"Event Bookings daily task failed: {name}",
                message=frappe.get_traceback(),
            )


def hourly():
    """Hourly scheduled tasks — reserved for future use."""
    pass


def sync_invoice_payment_status():
    """
    Transition Invoiced → Paid when the linked Sales Invoice is marked paid.

    Single UPDATE JOIN replaces the previous N+1 loop.
    Uses direct SQL db_set bypass — intentional and documented: the Invoiced → Paid
    transition has no side-effects beyond the status field (no documents to create,
    no cost centers to set up), so the full controller chain is unneeded here.
    """
    frappe.db.sql(
        """
        UPDATE `tabEvent Booking` eb
        INNER JOIN `tabSales Invoice` si ON si.name = eb.sales_invoice
        SET eb.booking_status = 'Paid',
            eb.modified = NOW(),
            eb.modified_by = 'Administrator'
        WHERE eb.booking_status = 'Invoiced'
          AND eb.sales_invoice IS NOT NULL
          AND si.status = 'Paid'
        """
    )
    frappe.db.commit()


def send_pre_event_reminders(days=3):
    """
    Send reminder emails to Event Managers T-3 and T-1 days before the event.

    Idempotent: uses reminder_sent_3d / reminder_sent_1d flag fields to ensure
    each reminder is sent at most once per booking, even if the scheduler runs
    multiple times (e.g. after a worker restart or a cron backfill).
    """
    sent_flag = "reminder_sent_3d" if days == 3 else "reminder_sent_1d"
    target_date = add_days(today(), days)
    events = frappe.get_all(
        "Event Booking",
        filters={
            "event_date": target_date,
            "booking_status": ("in", ["In Preparation", "Confirmed"]),
            sent_flag: 0,
        },
        fields=["name", "event_name", "event_date"],
    )
    for ev in events:
        try:
            _notify_event_managers(
                ev,
                subject=f"Reminder: Event '{ev.event_name}' is on {ev.event_date}",
                message=(
                    f"<p>This is a {days}-day reminder for the event "
                    f"<b>{ev.event_name}</b> ({ev.name}) scheduled on "
                    f"<b>{ev.event_date}</b>.</p>"
                    "<p>Please ensure all preparations are on track.</p>"
                ),
            )
            # Mark as sent so repeated scheduler runs skip this booking.
            frappe.db.set_value(
                "Event Booking", ev.name, sent_flag, 1, update_modified=False
            )
        except Exception:
            frappe.log_error(
                title=f"Pre-event reminder failed for {ev.name}",
                message=frappe.get_traceback(),
            )


def send_unstaffed_alerts():
    """
    Alert Event Managers when staff requirements are not fully met.

    Single JOIN query replaces the previous N+1 pattern (frappe.get_doc per event).
    Groups results in Python to send one email per event rather than one per row.
    """
    rows = frappe.db.sql(
        """
        SELECT
            eb.name                          AS event_name,
            eb.event_name                    AS event_title,
            esr.designation                  AS designation,
            esr.qty_required                 AS qty_required,
            COALESCE(esr.qty_assigned, 0)    AS qty_assigned
        FROM `tabEvent Booking` eb
        INNER JOIN `tabEvent Staff Requirement` esr ON esr.parent = eb.name
        WHERE eb.booking_status = 'In Preparation'
          AND COALESCE(esr.qty_assigned, 0) < esr.qty_required
        ORDER BY eb.name
        """,
        as_dict=True,
    )

    if not rows:
        return

    # Group understaffed lines by event
    from collections import defaultdict
    gaps   = defaultdict(list)
    titles = {}
    for row in rows:
        gaps[row.event_name].append(
            f"{row.designation}: {row.qty_assigned}/{row.qty_required} assigned"
        )
        titles[row.event_name] = row.event_title

    for event_name, lines in gaps.items():
        try:
            doc = frappe._dict(
                name=event_name,
                event_name=titles[event_name],
                doctype="Event Booking",
            )
            message = (
                f"<p>Event <b>{doc.event_name}</b> ({doc.name}) is under-staffed:</p>"
                + "<ul>"
                + "".join(f"<li>{line}</li>" for line in lines)
                + "</ul>"
            )
            _notify_event_managers(
                doc,
                subject=f"Under-staffed Alert: {doc.event_name}",
                message=message,
            )
        except Exception:
            frappe.log_error(
                title=f"Unstaffed alert failed for {event_name}",
                message=frappe.get_traceback(),
            )


def _notify_event_managers(doc, subject, message):
    """Send an email to all active users with the Event Manager role."""
    managers = get_event_managers()
    if not managers:
        return

    for user in managers:
        try:
            frappe.sendmail(
                recipients=[user.email],
                subject=subject,
                message=message,
                reference_doctype=doc.doctype,
                reference_name=doc.name,
            )
        except Exception:
            frappe.log_error(
                title=f"Failed to send event notification to {user.email}",
                message=frappe.get_traceback(),
            )


def get_event_managers():
    """Return all active users with the Event Manager role."""
    return frappe.get_all(
        "User",
        filters={
            "enabled": 1,
            "name": (
                "in",
                frappe.get_all("Has Role", filters={"role": "Event Manager"}, pluck="parent"),
            ),
        },
        fields=["email"],
    )
