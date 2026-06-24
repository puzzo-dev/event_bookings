"""
Custom dashboard chart source functions for Event Bookings.

These charts require ERPNext (Sales Invoice, Sales Order, Quotation are
ERPNext doctypes).  They are registered as Custom chart sources and will
throw if accessed without ERPNext installed.
"""

import frappe
from frappe import _
from frappe.utils import add_months, today, getdate
from frappe.utils.data import get_timespan_date_range


_CHART_ROLES = ["Event Manager", "Sales Manager", "Accounts User", "System Manager"]


def get_event_chart_filters():
    """
    Filter configuration shown in the 'Set Filters' popup on all 4 custom charts.
    Returns company (Link) + date range so users can slice by company on multi-company sites.
    """
    return [
        {
            "fieldname": "company",
            "label": "Company",
            "fieldtype": "Link",
            "options": "Company",
        },
        {
            "fieldname": "start_date",
            "label": "From Date",
            "fieldtype": "Date",
        },
        {
            "fieldname": "end_date",
            "label": "To Date",
            "fieldtype": "Date",
        },
    ]


@frappe.whitelist()
def get_monthly_events_chart(
    filters=None, chart_name=None, timespan=None, start_date=None, end_date=None,
    company=None, group_by=None, **kwargs
):
    """
    Monthly Events — count of Event Bookings grouped by event_date month.
    Supports optional grouping by Event Type (one dataset per type).
    Default: last 12 months.  Filterable by company, timespan, or custom date range.
    """
    _require_chart_role()
    start_date, end_date = _resolve_dates(timespan, start_date, end_date, default_months=-11)

    company_filter = "AND company = %(company)s" if company else ""
    params = {"start_date": start_date, "end_date": end_date, "company": company}
    labels = _month_labels(start_date, end_date)

    if group_by == "Event Type":
        rows = frappe.db.sql(
            f"""
            SELECT
                DATE_FORMAT(event_date, '%%Y-%%m') AS period,
                COALESCE(event_type, 'Other') AS event_type,
                COUNT(*) AS cnt
            FROM `tabEvent Booking`
            WHERE event_date BETWEEN %(start_date)s AND %(end_date)s
              AND booking_status != 'Cancelled'
              {company_filter}
            GROUP BY period, event_type
            ORDER BY period ASC
            """,
            params,
            as_dict=True,
        )
        types = sorted(set(r.event_type for r in rows))
        datasets = []
        for et in types:
            et_map = {r.period: r.cnt for r in rows if r.event_type == et}
            datasets.append({"name": et, "values": [et_map.get(l, 0) for l in labels]})
        return {"labels": labels, "datasets": datasets}

    rows = frappe.db.sql(
        f"""
        SELECT
            DATE_FORMAT(event_date, '%%Y-%%m') AS period,
            COUNT(*) AS cnt
        FROM `tabEvent Booking`
        WHERE event_date BETWEEN %(start_date)s AND %(end_date)s
          AND booking_status != 'Cancelled'
          {company_filter}
        GROUP BY period
        ORDER BY period ASC
        """,
        params,
        as_dict=True,
    )
    row_map = {r.period: r.cnt for r in rows}
    return {
        "labels": labels,
        "datasets": [{"name": _("Events"), "values": [row_map.get(l, 0) for l in labels]}],
    }


@frappe.whitelist()
def get_revenue_trend_chart(
    filters=None, chart_name=None, timespan=None, start_date=None, end_date=None,
    company=None, group_by=None, **kwargs
):
    """
    Event Revenue Trend — sum of total_actual on Event Bookings grouped by event_date month.
    Supports optional grouping by Event Type (one dataset per type).
    Default: last 12 months.  Filterable by company, timespan, or custom date range.
    """
    _require_chart_role()
    start_date, end_date = _resolve_dates(timespan, start_date, end_date, default_months=-11)

    company_filter = "AND company = %(company)s" if company else ""
    params = {"start_date": start_date, "end_date": end_date, "company": company}
    labels = _month_labels(start_date, end_date)

    if group_by == "Event Type":
        rows = frappe.db.sql(
            f"""
            SELECT
                DATE_FORMAT(event_date, '%%Y-%%m') AS period,
                COALESCE(event_type, 'Other') AS event_type,
                SUM(total_actual) AS revenue
            FROM `tabEvent Booking`
            WHERE event_date BETWEEN %(start_date)s AND %(end_date)s
              AND booking_status != 'Cancelled'
              {company_filter}
            GROUP BY period, event_type
            ORDER BY period ASC
            """,
            params,
            as_dict=True,
        )
        types = sorted(set(r.event_type for r in rows))
        datasets = []
        for et in types:
            et_map = {r.period: (r.revenue or 0) for r in rows if r.event_type == et}
            datasets.append({"name": et, "values": [et_map.get(l, 0) for l in labels]})
        return {"labels": labels, "datasets": datasets}

    rows = frappe.db.sql(
        f"""
        SELECT
            DATE_FORMAT(event_date, '%%Y-%%m') AS period,
            SUM(total_actual) AS revenue
        FROM `tabEvent Booking`
        WHERE event_date BETWEEN %(start_date)s AND %(end_date)s
          AND booking_status != 'Cancelled'
          {company_filter}
        GROUP BY period
        ORDER BY period ASC
        """,
        params,
        as_dict=True,
    )
    row_map = {r.period: (r.revenue or 0) for r in rows}
    return {
        "labels": labels,
        "datasets": [{"name": _("Revenue"), "values": [row_map.get(l, 0) for l in labels]}],
    }


@frappe.whitelist()
def get_upcoming_events_count(**kwargs):
    """
    Count of non-cancelled Event Bookings with event_date >= today.
    Used by the 'Upcoming Events' Number Card (type: Custom) so the
    filter can reference today's date at query time instead of a static string.
    """
    _require_chart_role()
    return frappe.db.count(
        "Event Booking",
        filters={
            "event_date": [">=", today()],
            "booking_status": ["not in", ["Cancelled"]],
        },
    )


def _resolve_dates(timespan, start_date, end_date, default_months=-5):
    """
    Resolve start/end dates for a chart function.
    Priority: explicit start_date/end_date > timespan > default (last N months).
    When timespan == 'Date Range', falls through to start_date/end_date or default.
    Timespan values match Frappe's get_timespan_date_range keys (case-insensitive).
    """
    if start_date and end_date:
        return start_date, end_date
    if timespan and timespan.lower() != "date range":
        result = get_timespan_date_range(timespan.lower())
        if result:
            return str(result[0]), str(result[1])
    # 'Date Range' selected but no dates provided, or no timespan — use default
    return add_months(today(), default_months), today()


def _require_erpnext():
    if "erpnext" not in frappe.get_installed_apps():
        frappe.throw(_("This chart requires ERPNext to be installed."))


def _require_chart_role():
    """Restrict chart data APIs to authorised roles."""
    frappe.only_for(_CHART_ROLES)


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
    filters=None, chart_name=None, timespan=None, start_date=None, end_date=None, company=None, **kwargs
):
    """
    Deals Completed — amount billed via submitted Sales Invoices linked to Event Bookings.
    Default: last 6 months.  Filterable by company, timespan, or custom date range.
    """
    _require_chart_role()
    _require_erpnext()

    start_date, end_date = _resolve_dates(timespan, start_date, end_date)

    company_filter = "AND si.company = %(company)s" if company else ""
    rows = frappe.db.sql(
        f"""
        SELECT
            DATE_FORMAT(si.posting_date, '%%Y-%%m') AS period,
            SUM(si.grand_total)                      AS amount
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.event_booking IS NOT NULL
          AND si.event_booking != ''
          AND si.posting_date BETWEEN %(start_date)s AND %(end_date)s
          {company_filter}
        GROUP BY period
        ORDER BY period ASC
        """,
        {"start_date": start_date, "end_date": end_date, "company": company},
        as_dict=True,
    )

    row_map = {r.period: r for r in rows}
    labels = _month_labels(start_date, end_date)

    return {
        "labels": labels,
        "datasets": [
            {
                "name": _("Total"),
                "values": [row_map.get(l, {}).get("amount", 0) or 0 for l in labels],
            },
        ],
    }


@frappe.whitelist()
def get_deals_lost_chart(
    filters=None, chart_name=None, timespan=None, start_date=None, end_date=None, company=None, **kwargs
):
    """
    Deals Lost — pipeline value lost when bookings are cancelled post-quotation.
    Default: last 6 months.  Filterable by company, timespan, or custom date range.
    """
    _require_chart_role()
    _require_erpnext()

    start_date, end_date = _resolve_dates(timespan, start_date, end_date)

    company_filter = "AND eb.company = %(company)s" if company else ""
    rows = frappe.db.sql(
        f"""
        SELECT
            DATE_FORMAT(eb.modified, '%%Y-%%m') AS period,
            SUM(q.grand_total)                   AS amount
        FROM `tabEvent Booking` eb
        INNER JOIN `tabQuotation` q
            ON q.name = eb.quotation
        WHERE eb.booking_status = 'Cancelled'
          AND eb.quotation IS NOT NULL
          AND eb.quotation != ''
          AND eb.modified BETWEEN %(start_date)s AND %(end_date)s
          {company_filter}
        GROUP BY period
        ORDER BY period ASC
        """,
        {"start_date": start_date, "end_date": end_date, "company": company},
        as_dict=True,
    )

    row_map = {r.period: r for r in rows}
    labels = _month_labels(start_date, end_date)

    return {
        "labels": labels,
        "datasets": [
            {
                "name": _("Pipeline Lost"),
                "values": [row_map.get(l, {}).get("amount", 0) or 0 for l in labels],
            },
        ],
    }


@frappe.whitelist()
def get_inquiry_conversion_chart(
    filters=None, chart_name=None, timespan=None, start_date=None, end_date=None, company=None, **kwargs
):
    """
    Inquiry vs Conversion — standalone chart, no ERPNext required.

    Inquiry   = any new Event Booking created in the period (someone contacted us).
    Converted = bookings that reached Confirmed or beyond in the period
                (they committed to the event).

    Works on plain Frappe because it only queries Event Booking.
    """
    _require_chart_role()
    start_date, end_date = _resolve_dates(timespan, start_date, end_date)

    company_filter = "AND company = %(company)s" if company else ""
    params = {"start_date": start_date, "end_date": end_date, "company": company}

    # New inquiries: bookings created in the period
    inquiry_rows = frappe.db.sql(
        f"""
        SELECT
            DATE_FORMAT(booking_date, '%%Y-%%m') AS period,
            COUNT(*) AS inquiry_count
        FROM `tabEvent Booking`
        WHERE booking_date BETWEEN %(start_date)s AND %(end_date)s
          {company_filter}
        GROUP BY period
        ORDER BY period ASC
        """,
        params,
        as_dict=True,
    )

    # Converted: bookings that moved to Confirmed or beyond in the period
    converted_rows = frappe.db.sql(
        f"""
        SELECT
            DATE_FORMAT(modified, '%%Y-%%m') AS period,
            COUNT(*) AS converted_count
        FROM `tabEvent Booking`
        WHERE booking_status IN (
            'Confirmed', 'In Preparation', 'Executed', 'Invoiced', 'Paid'
        )
        AND modified BETWEEN %(start_date)s AND %(end_date)s
          {company_filter}
        GROUP BY period
        ORDER BY period ASC
        """,
        params,
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
    filters=None, chart_name=None, timespan=None, start_date=None, end_date=None, company=None, **kwargs
):
    """
    Lead Conversion Funnel — ERPNext + HRMS only.

    Shows the pipeline stages month-by-month:
      Leads booked → Quotations issued → Sales Orders confirmed → Invoiced

    Requires ERPNext because Lead, Quotation, Sales Order are ERPNext doctypes.
    """
    _require_chart_role()
    _require_erpnext()

    start_date, end_date = _resolve_dates(timespan, start_date, end_date)
    params = {"start_date": start_date, "end_date": end_date, "company": company}
    eb_company_filter = "AND company = %(company)s" if company else ""
    doc_company_filter = "AND company = %(company)s" if company else ""

    # Leads that had an Event Booking created for them
    lead_rows = frappe.db.sql(
        f"""
        SELECT DATE_FORMAT(booking_date, '%%Y-%%m') AS period, COUNT(*) AS cnt
        FROM `tabEvent Booking`
        WHERE party_type = 'Lead'
          AND booking_date BETWEEN %(start_date)s AND %(end_date)s
          {eb_company_filter}
        GROUP BY period ORDER BY period
        """,
        params, as_dict=True,
    )

    # Quotations submitted against event bookings
    qt_rows = frappe.db.sql(
        f"""
        SELECT DATE_FORMAT(q.transaction_date, '%%Y-%%m') AS period, COUNT(*) AS cnt
        FROM `tabQuotation` q
        WHERE q.docstatus = 1
          AND q.event_booking IS NOT NULL AND q.event_booking != ''
          AND q.transaction_date BETWEEN %(start_date)s AND %(end_date)s
          {doc_company_filter}
        GROUP BY period ORDER BY period
        """,
        params, as_dict=True,
    )

    # Sales Orders submitted against event bookings
    so_rows = frappe.db.sql(
        f"""
        SELECT DATE_FORMAT(so.transaction_date, '%%Y-%%m') AS period, COUNT(*) AS cnt
        FROM `tabSales Order` so
        WHERE so.docstatus = 1
          AND so.event_booking IS NOT NULL AND so.event_booking != ''
          AND so.transaction_date BETWEEN %(start_date)s AND %(end_date)s
          {doc_company_filter}
        GROUP BY period ORDER BY period
        """,
        params, as_dict=True,
    )

    # Submitted Sales Invoices against event bookings (deal closed)
    si_rows = frappe.db.sql(
        f"""
        SELECT DATE_FORMAT(si.posting_date, '%%Y-%%m') AS period, COUNT(*) AS cnt
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.event_booking IS NOT NULL AND si.event_booking != ''
          AND si.posting_date BETWEEN %(start_date)s AND %(end_date)s
          {doc_company_filter}
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
