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


@frappe.whitelist()
def get_inquiry_conversion_chart(
    filters=None, chart_name=None, start_date=None, end_date=None, **kwargs
):
    """
    Inquiry vs Conversion — standalone chart, no ERPNext required.

    Inquiry   = any new Event Booking created in the period (someone contacted us).
    Converted = bookings that reached Confirmed or beyond in the period
                (they committed to the event).

    Works on plain Frappe because it only queries Event Booking.
    """
    if not start_date:
        start_date = add_months(today(), -11)
    if not end_date:
        end_date = today()

    # New inquiries: bookings created in the period
    inquiry_rows = frappe.db.sql(
        """
        SELECT
            DATE_FORMAT(booking_date, '%%Y-%%m') AS period,
            COUNT(*) AS inquiry_count
        FROM `tabEvent Booking`
        WHERE booking_date BETWEEN %(start_date)s AND %(end_date)s
        GROUP BY period
        ORDER BY period ASC
        """,
        {"start_date": start_date, "end_date": end_date},
        as_dict=True,
    )

    # Converted: bookings that moved to Confirmed or beyond in the period
    converted_rows = frappe.db.sql(
        """
        SELECT
            DATE_FORMAT(modified, '%%Y-%%m') AS period,
            COUNT(*) AS converted_count
        FROM `tabEvent Booking`
        WHERE booking_status IN (
            'Confirmed', 'In Preparation', 'Executed', 'Invoiced', 'Paid'
        )
        AND modified BETWEEN %(start_date)s AND %(end_date)s
        GROUP BY period
        ORDER BY period ASC
        """,
        {"start_date": start_date, "end_date": end_date},
        as_dict=True,
    )

    labels = _month_labels(start_date, end_date)
    inquiry_map = {r.period: r.inquiry_count for r in inquiry_rows}
    converted_map = {r.period: r.converted_count for r in converted_rows}

    return {
        "labels": labels,
        "datasets": [
            {
                "name": _("Inquiries"),
                "values": [inquiry_map.get(l, 0) for l in labels],
            },
            {
                "name": _("Converted"),
                "values": [converted_map.get(l, 0) for l in labels],
            },
        ],
    }


@frappe.whitelist()
def get_lead_conversion_funnel_chart(
    filters=None, chart_name=None, start_date=None, end_date=None, **kwargs
):
    """
    Lead Conversion Funnel — ERPNext + HRMS only.

    Shows the pipeline stages month-by-month:
      Leads booked → Quotations issued → Sales Orders confirmed → Invoiced

    Requires ERPNext because Lead, Quotation, Sales Order are ERPNext doctypes.
    """
    _require_erpnext()

    if not start_date:
        start_date = add_months(today(), -11)
    if not end_date:
        end_date = today()

    params = {"start_date": start_date, "end_date": end_date}

    # Leads that had an Event Booking created for them
    lead_rows = frappe.db.sql(
        """
        SELECT DATE_FORMAT(booking_date, '%%Y-%%m') AS period, COUNT(*) AS cnt
        FROM `tabEvent Booking`
        WHERE party_type = 'Lead'
          AND booking_date BETWEEN %(start_date)s AND %(end_date)s
        GROUP BY period ORDER BY period
        """,
        params, as_dict=True,
    )

    # Quotations submitted against event bookings
    qt_rows = frappe.db.sql(
        """
        SELECT DATE_FORMAT(q.transaction_date, '%%Y-%%m') AS period, COUNT(*) AS cnt
        FROM `tabQuotation` q
        WHERE q.docstatus = 1
          AND q.event_booking IS NOT NULL AND q.event_booking != ''
          AND q.transaction_date BETWEEN %(start_date)s AND %(end_date)s
        GROUP BY period ORDER BY period
        """,
        params, as_dict=True,
    )

    # Sales Orders submitted against event bookings
    so_rows = frappe.db.sql(
        """
        SELECT DATE_FORMAT(so.transaction_date, '%%Y-%%m') AS period, COUNT(*) AS cnt
        FROM `tabSales Order` so
        WHERE so.docstatus = 1
          AND so.event_booking IS NOT NULL AND so.event_booking != ''
          AND so.transaction_date BETWEEN %(start_date)s AND %(end_date)s
        GROUP BY period ORDER BY period
        """,
        params, as_dict=True,
    )

    # Submitted Sales Invoices against event bookings (deal closed)
    si_rows = frappe.db.sql(
        """
        SELECT DATE_FORMAT(si.posting_date, '%%Y-%%m') AS period, COUNT(*) AS cnt
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.event_booking IS NOT NULL AND si.event_booking != ''
          AND si.posting_date BETWEEN %(start_date)s AND %(end_date)s
        GROUP BY period ORDER BY period
        """,
        params, as_dict=True,
    )

    labels = _month_labels(start_date, end_date)

    def _vals(rows):
        m = {r.period: r.cnt for r in rows}
        return [m.get(l, 0) for l in labels]

    return {
        "labels": labels,
        "datasets": [
            {"name": _("Leads Booked"),      "values": _vals(lead_rows)},
            {"name": _("Quotations Issued"),  "values": _vals(qt_rows)},
            {"name": _("Orders Confirmed"),   "values": _vals(so_rows)},
            {"name": _("Invoiced"),           "values": _vals(si_rows)},
        ],
    }
