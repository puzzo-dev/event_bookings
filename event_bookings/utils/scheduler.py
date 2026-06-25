import frappe


def daily():
    """Daily scheduled tasks."""
    for name, task in (
        ("sync_invoice_payment_status", sync_invoice_payment_status),
        ("send_unstaffed_alerts", send_unstaffed_alerts),
    ):
        try:
            task()
        except Exception:
            frappe.log_error(
                title=f"Event Bookings daily task failed: {name}",
                message=frappe.get_traceback(),
            )


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
            eb.modified_by = %s
        WHERE eb.booking_status = 'Invoiced'
          AND eb.sales_invoice IS NOT NULL
          AND si.status = 'Paid'
        """,
        (frappe.session.user,),
    )
    frappe.db.commit()


def send_unstaffed_alerts():
    """
    Alert Event Managers when staff requirements are not fully met.

    Detects understaffed bookings via SQL, then delegates email sending to the
    'Event Under-Staffed Alert' Frappe Notification — keeping template and
    recipient management in the Notification DocType rather than in code.
    """
    events = frappe.db.sql(
        """
        SELECT DISTINCT eb.name
        FROM `tabEvent Booking` eb
        INNER JOIN `tabEvent Staff Requirement` esr ON esr.parent = eb.name
        WHERE eb.booking_status = 'In Preparation'
          AND COALESCE(esr.qty_assigned, 0) < esr.qty_required
        """,
        as_dict=True,
    )
    if not events:
        return

    try:
        notification = frappe.get_doc("Notification", "Event Under-Staffed Alert")
    except frappe.DoesNotExistError:
        frappe.log_error(
            title="Event Under-Staffed Alert notification not found",
            message="Ensure fixtures are loaded via bench migrate.",
        )
        return

    for row in events:
        try:
            doc = frappe.get_doc("Event Booking", row.name)
            notification.send(doc)
        except Exception:
            frappe.log_error(
                title=f"Unstaffed alert failed for {row.name}",
                message=frappe.get_traceback(),
            )
