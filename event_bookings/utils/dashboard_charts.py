"""
Custom dashboard chart source functions for Event Bookings.

These charts require ERPNext (Sales Invoice, Sales Order, Quotation are
ERPNext doctypes).  They are registered as Custom chart sources and will
throw if accessed without ERPNext installed.
"""

import frappe
from frappe import _
from frappe.utils import add_months, today, getdate


def _require_erpnext():
    if "erpnext" not in frappe.get_installed_apps():
        frappe.throw(_("This chart requires ERPNext to be installed."))


def _month_labels(start_date, end_date):
    """Return ordered list of YYYY-MM strings covering start_date → end_date."""
    labels = []
    current = getdate(start_date).replace(day=1)
    end = getdate(end_date).replace(day=1)
    while current <= end:
        labels.append(current.strftime("%Y-%m"))
        month = current.month + 1
        year = current.year + (1 if month > 12 else 0)
        current = current.replace(year=year, month=(month - 1) % 12 + 1)
    return labels


@frappe.whitelist()
def get_deals_completed_chart(
    filters=None, chart_name=None, start_date=None, end_date=None, **kwargs
):
    """
    Deals Completed — submitted Sales Invoices linked to Event Bookings.

    A deal is considered complete when a Sales Invoice is submitted against
    a Sales Order that originated from a Quotation linked to an Event Booking.
    The Sales Invoice carries the final billed amount.
    """
    _require_erpnext()

    if not start_date:
        start_date = add_months(today(), -11)
    if not end_date:
        end_date = today()

    rows = frappe.db.sql(
        """
        SELECT
            DATE_FORMAT(si.posting_date, '%%Y-%%m') AS period,
            COUNT(*)                                 AS deal_count,
            SUM(si.grand_total)                      AS amount
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.event_booking IS NOT NULL
          AND si.event_booking != ''
          AND si.posting_date BETWEEN %(start_date)s AND %(end_date)s
        GROUP BY period
        ORDER BY period ASC
        """,
        {"start_date": start_date, "end_date": end_date},
        as_dict=True,
    )

    row_map = {r.period: r for r in rows}
    labels = _month_labels(start_date, end_date)

    return {
        "labels": labels,
        "datasets": [
            {
                "name": _("Deals Completed"),
                "values": [row_map.get(l, {}).get("deal_count", 0) for l in labels],
            },
            {
                "name": _("Amount"),
                "values": [row_map.get(l, {}).get("amount", 0) or 0 for l in labels],
            },
        ],
    }


@frappe.whitelist()
def get_deals_lost_chart(
    filters=None, chart_name=None, start_date=None, end_date=None, **kwargs
):
    """
    Deals Lost — Event Bookings cancelled after a Quotation was issued.

    A deal is lost when a booking is cancelled having reached at least the
    Quoted stage.  The amount represents the pipeline value that walked away
    (Quotation grand_total).
    """
    _require_erpnext()

    if not start_date:
        start_date = add_months(today(), -11)
    if not end_date:
        end_date = today()

    rows = frappe.db.sql(
        """
        SELECT
            DATE_FORMAT(eb.modified, '%%Y-%%m') AS period,
            COUNT(*)                             AS deal_count,
            SUM(q.grand_total)                   AS amount
        FROM `tabEvent Booking` eb
        INNER JOIN `tabQuotation` q
            ON q.name = eb.quotation
        WHERE eb.booking_status = 'Cancelled'
          AND eb.quotation IS NOT NULL
          AND eb.quotation != ''
          AND eb.modified BETWEEN %(start_date)s AND %(end_date)s
        GROUP BY period
        ORDER BY period ASC
        """,
        {"start_date": start_date, "end_date": end_date},
        as_dict=True,
    )

    row_map = {r.period: r for r in rows}
    labels = _month_labels(start_date, end_date)

    return {
        "labels": labels,
        "datasets": [
            {
                "name": _("Deals Lost"),
                "values": [row_map.get(l, {}).get("deal_count", 0) for l in labels],
            },
            {
                "name": _("Pipeline Lost"),
                "values": [row_map.get(l, {}).get("amount", 0) or 0 for l in labels],
            },
        ],
    }
