import frappe

from event_bookings.event_bookings.doctype.event_booking.event_booking import _sql_items_total


def _update_linked_event_booking(doc, recalculate_totals=False, **field_updates):
    """
    Apply targeted DB updates to the linked Event Booking without triggering
    the full controller save chain.

    Using eb.save() here would cause:
    - Re-running status transition validation (unnecessary for link syncs)
    - Google Calendar API call on every Quotation/SO/SI submit
    - A circular doc-fetch: validate() → calculate_totals() → frappe.get_doc(Quotation)
      on the same document that triggered this hook

    Instead we use frappe.db.set_value for atomic field updates and call
    _sql_items_total() directly for revenue recalculation — no Document objects loaded.

    Errors are logged and surfaced via msgprint so that failures in Event Booking
    back-linking do not block the ERPNext document from being processed.
    """
    if not doc.event_booking:
        return
    try:
        updates = dict(field_updates)

        if recalculate_totals:
            # Read current link fields from DB (merging any just-updated values)
            eb_links = frappe.db.get_value(
                "Event Booking",
                doc.event_booking,
                ["quotation", "sales_order", "sales_invoice"],
                as_dict=True,
            )
            # Prefer values from field_updates (just set) over what is in DB
            quotation     = updates.get("quotation",     eb_links.quotation)
            sales_order   = updates.get("sales_order",   eb_links.sales_order)
            sales_invoice = updates.get("sales_invoice", eb_links.sales_invoice)

            total_estimated = _sql_items_total("Quotation", quotation)
            total_actual    = _sql_items_total("Sales Order", sales_order)
            if not total_actual and sales_invoice:
                total_actual = _sql_items_total("Sales Invoice", sales_invoice)

            updates["total_estimated"] = total_estimated
            updates["total_actual"]    = total_actual

        if updates:
            frappe.db.set_value("Event Booking", doc.event_booking, updates)

    except Exception:
        frappe.log_error(
            title=f"Event Booking link failed on {doc.doctype} {doc.name}",
            message=frappe.get_traceback(),
        )
        frappe.msgprint(
            f"Could not update Event Booking {doc.event_booking}. Check the Error Log.",
            indicator="orange",
            alert=True,
        )


# ---------------------------------------------------------------------------
# Quotation hooks
# ---------------------------------------------------------------------------

def on_quotation_submit(doc, method):
    _update_linked_event_booking(doc, recalculate_totals=True, quotation=doc.name)


def on_quotation_update(doc, method):
    if doc.docstatus == 1:
        _update_linked_event_booking(doc, recalculate_totals=True)


def on_quotation_cancel(doc, method):
    _update_linked_event_booking(doc, recalculate_totals=True, quotation=None)


# ---------------------------------------------------------------------------
# Sales Order hooks
# ---------------------------------------------------------------------------

def on_sales_order_submit(doc, method):
    _update_linked_event_booking(doc, recalculate_totals=True, sales_order=doc.name)


def on_sales_order_update(doc, method):
    if doc.docstatus == 1:
        _update_linked_event_booking(doc, recalculate_totals=True)


def on_sales_order_cancel(doc, method):
    _update_linked_event_booking(doc, recalculate_totals=True, sales_order=None)


# ---------------------------------------------------------------------------
# Sales Invoice hooks
# ---------------------------------------------------------------------------

def on_sales_invoice_submit(doc, method):
    _update_linked_event_booking(doc, recalculate_totals=True, sales_invoice=doc.name)


def on_sales_invoice_update(doc, method):
    if doc.docstatus == 1:
        _update_linked_event_booking(doc, recalculate_totals=True)


def on_sales_invoice_cancel(doc, method):
    _update_linked_event_booking(doc, recalculate_totals=True, sales_invoice=None)


# ---------------------------------------------------------------------------
# Stock Entry hooks
# ---------------------------------------------------------------------------

def on_stock_entry_submit(doc, method):
    if doc.stock_entry_type == "Material Issue":
        _update_linked_event_booking(doc)


def on_stock_entry_cancel(doc, method):
    if doc.stock_entry_type == "Material Issue":
        _update_linked_event_booking(doc)


# ---------------------------------------------------------------------------
# Shift Assignment hooks
# ---------------------------------------------------------------------------

def on_shift_assignment_update(doc, method):
    """
    Sync qty_assigned counts on Event Staff Requirement rows after a
    Shift Assignment changes state.

    Single UPDATE JOIN replaces the previous N+1 pattern (frappe.db.set_value
    per child row).  Uses a derived-table subquery so all rows are updated in
    one round-trip without loading the Event Booking document at all.
    """
    if not doc.event_booking:
        return
    try:
        frappe.db.sql(
            """
            UPDATE `tabEvent Staff Requirement` esr
            LEFT JOIN (
                SELECT LOWER(TRIM(designation)) AS desig, COUNT(*) AS cnt
                FROM `tabShift Assignment`
                WHERE event_booking = %(booking)s AND docstatus < 2
                GROUP BY LOWER(TRIM(designation))
            ) counts ON counts.desig = LOWER(TRIM(esr.designation))
            SET esr.qty_assigned = COALESCE(counts.cnt, 0)
            WHERE esr.parent = %(booking)s
            """,
            {"booking": doc.event_booking},
        )
        frappe.db.commit()
    except Exception:
        frappe.log_error(
            title=f"Staff count sync failed for Event Booking {doc.event_booking}",
            message=frappe.get_traceback(),
        )
