import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils import today, getdate, flt

from event_bookings.utils.erpnext_bridge import is_erpnext_installed, make_customer_from_lead


# Whitelisted table-to-doctype mapping for SQL totals.
# Hardcoded dict ensures no user input can reach the table name in the f-string below.
_ITEMS_TABLE = {
    "Quotation":     "tabQuotation Item",
    "Sales Order":   "tabSales Order Item",
    "Sales Invoice": "tabSales Invoice Item",
}


class EventBooking(Document):
    def validate(self):
        self.validate_dates()
        self.validate_party()
        self._fetch_contact_phone()

    def before_save(self):
        self.calculate_totals()
        # has_status_changed() fetches and caches old_status once.
        # _validate_status_transition() reuses the cache — avoids a second DB hit.
        if self.has_status_changed():
            self._validate_status_transition()
            self.handle_status_transition()

    def _validate_status_transition(self):
        if self.is_new():
            return
        old_status = self._cached_old_status
        if old_status is None or old_status == self.booking_status:
            return
        # All status transitions are allowed; validation still runs so the
        # transition hook (notifications, linked-doc cancellation) fires reliably.

    # -----------------------------------------------------------------
    # Validations
    # -----------------------------------------------------------------

    def calculate_totals(self):
        """
        Sum line-item amounts from linked documents via SQL aggregation.
        Avoids loading full Document objects (and child tables) inside validate.
        """
        self.total_estimated = _sql_items_total("Quotation", self.quotation)
        self.total_actual = _sql_items_total("Sales Order", self.sales_order)
        if not self.total_actual and self.sales_invoice:
            self.total_actual = _sql_items_total("Sales Invoice", self.sales_invoice)

    def recalculate_totals(self):
        """
        Recalculate and persist totals via targeted db_set.
        Does NOT trigger the full controller save chain — no status transition
        validation, no Google Calendar sync, no re-entrant hooks.
        """
        self.calculate_totals()
        self.db_set({
            "total_estimated": self.total_estimated,
            "total_actual": self.total_actual,
        }, update_modified=False)

    def validate_dates(self):
        if self.event_date and not self.is_new():
            if self.has_value_changed("event_date"):
                if getdate(self.event_date) < getdate(today()):
                    frappe.throw(_("Event Date cannot be moved to a past date on an existing booking."))

    def validate_party(self):
        if self.party_type in ("Customer", "Lead") and self.party_name:
            if not frappe.db.exists(self.party_type, self.party_name):
                frappe.throw(
                    _("{0} '{1}' does not exist. Please select a valid {0}.").format(
                        self.party_type, self.party_name
                    )
                )

    def _fetch_contact_phone(self):
        """Auto-populate contact_phone from the linked Lead or Customer.

        For Lead: reads mobile_no / whatsapp_no / phone directly.
        For Customer: reads from the primary Contact linked via Dynamic Link.
        """
        if not self.party_type or not self.party_name:
            self.contact_phone = None
            return

        if self.party_type == "Lead":
            self.contact_phone = (
                frappe.db.get_value("Lead", self.party_name, "mobile_no")
                or frappe.db.get_value("Lead", self.party_name, "phone")
            )
        elif self.party_type == "Customer":
            contact_name = frappe.get_all(
                "Dynamic Link",
                filters={
                    "link_doctype": "Customer",
                    "link_name": self.party_name,
                    "parenttype": "Contact",
                },
                fields=["parent"],
                order_by="idx asc",
                limit=1,
            )
            if contact_name:
                self.contact_phone = (
                    frappe.db.get_value("Contact", contact_name[0]["parent"], "mobile_no")
                    or frappe.db.get_value("Contact", contact_name[0]["parent"], "phone")
                )
            else:
                self.contact_phone = None

    # -----------------------------------------------------------------
    # Status Transition Hook
    # -----------------------------------------------------------------

    def has_status_changed(self):
        """
        Fetch old status once and cache it on the instance.
        _validate_status_transition() reuses _cached_old_status to avoid
        a second frappe.db.get_value call on the same field.
        """
        if self.is_new():
            self._cached_old_status = None
            return False
        old_status = frappe.db.get_value("Event Booking", self.name, "booking_status")
        self._cached_old_status = old_status
        return old_status != self.booking_status

    def handle_status_transition(self):
        status = self.booking_status

        if status == "In Preparation":
            self._notify_staff_requirements()

        elif status == "Cancelled":
            self.cancel_linked_documents()

    def _notify_staff_requirements(self):
        """
        When moving to In Preparation, alert managers about outstanding staffing gaps.

        HRMS Shift Assignment requires a named employee on every record and does not
        support unassigned placeholder slots.  Managers must create Shift Assignments
        manually via HR > Shift Assignment with event_booking set to this booking.
        """
        needed = []
        for req in self.get("staff_requirements") or []:
            gap = int(req.get("qty_required") or 0) - int(req.get("qty_assigned") or 0)
            if gap > 0:
                needed.append(f"{req.get('designation')}: {gap} slot(s) required")
        if needed:
            frappe.msgprint(
                "<b>Staff requirements outstanding.</b><br>"
                "Please create Shift Assignments in <b>HR &gt; Shift Assignment</b> "
                f"with the <i>Event Booking</i> field set to <b>{self.name}</b>:<ul>"
                + "".join(f"<li>{n}</li>" for n in needed)
                + "</ul>",
                title="Staff Assignment Needed",
                indicator="orange",
            )

    def cancel_linked_documents(self):
        """Enqueue cancellation of linked documents so saves never block on HTTP."""
        frappe.enqueue(
            "event_bookings.event_bookings.doctype.event_booking.event_booking"
            "._cancel_linked_documents_background",
            booking_name=self.name,
            queue="default",
            now=frappe.in_test,
        )

    # -----------------------------------------------------------------
    # Document Creation Helpers
    # -----------------------------------------------------------------


# ---------------------------------------------------------------------------
# Background worker — cancellation (runs via frappe.enqueue)
# ---------------------------------------------------------------------------

def _cancel_linked_documents_background(booking_name):
    """
    Cancel submitted documents linked to an Event Booking.

    Runs in a background worker (enqueued by cancel_linked_documents) so that
    HTTP requests to external services (doc.cancel() may trigger ERPNext ledger
    entries) never block the user-facing save request.
    """
    linked = [
        ("quotation",        "Quotation"),
        ("sales_order",      "Sales Order"),
        ("sales_invoice",    "Sales Invoice"),
    ]
    booking = frappe.db.get_value(
        "Event Booking",
        booking_name,
        ["quotation", "sales_order", "sales_invoice"],
        as_dict=True,
    ) or {}

    for field, doctype in linked:
        name = booking.get(field)
        if not name:
            continue
        try:
            doc = frappe.get_doc(doctype, name)
            if doc.docstatus == 1:
                if not frappe.has_permission(doctype, "cancel", doc):
                    frappe.log_error(
                        title=f"No cancel permission for {doctype} {name} "
                              f"(Event Booking {booking_name})",
                        message=f"User does not have cancel permission for {doctype} {name}",
                    )
                    continue
                doc.cancel()
        except Exception:
            frappe.log_error(
                title=f"Failed to cancel {doctype} {name} for Event Booking {booking_name}",
                message=frappe.get_traceback(),
            )

    # Cancel linked Stock Entries (reverse link via event_booking custom field on Stock Entry)
    for entry in frappe.get_all(
        "Stock Entry", filters={"event_booking": booking_name, "docstatus": 1}
    ):
        try:
            doc = frappe.get_doc("Stock Entry", entry.name)
            if not frappe.has_permission("Stock Entry", "cancel", doc):
                frappe.log_error(
                    title=f"No cancel permission for Stock Entry {entry.name}",
                    message=f"Event Booking: {booking_name}",
                )
                continue
            doc.cancel()
        except Exception:
            frappe.log_error(
                title=f"Failed to cancel Stock Entry {entry.name} "
                      f"for Event Booking {booking_name}",
                message=frappe.get_traceback(),
            )

    # Cancel linked Shift Assignments (queried by custom field, not a Link field)
    for shift in frappe.get_all(
        "Shift Assignment", filters={"event_booking": booking_name, "docstatus": 1}
    ):
        try:
            doc = frappe.get_doc("Shift Assignment", shift.name)
            if not frappe.has_permission("Shift Assignment", "cancel", doc):
                frappe.log_error(
                    title=f"No cancel permission for Shift Assignment {shift.name}",
                    message=f"Event Booking: {booking_name}",
                )
                continue
            doc.cancel()
        except Exception:
            frappe.log_error(
                title=f"Failed to cancel Shift Assignment {shift.name} "
                      f"for Event Booking {booking_name}",
                message=frappe.get_traceback(),
            )


# ---------------------------------------------------------------------------
# Module-level SQL helper — shared by controller and erpnext_hooks
# ---------------------------------------------------------------------------

def _sql_items_total(doctype, name):
    """
    Return the SUM of `amount` across all child rows of the given document.

    Safe from SQL injection:
    - `doctype` is validated against the hardcoded _ITEMS_TABLE whitelist.
    - `name` and `doctype` values are passed as %s parameters, never interpolated.
    """
    if not name:
        return 0.0
    table = _ITEMS_TABLE.get(doctype)
    if not table:
        frappe.log_error(
            title=f"Event Bookings: unknown doctype '{doctype}' in _sql_items_total"
        )
        return 0.0
    result = frappe.db.sql(
        f"SELECT SUM(amount) FROM `{table}` WHERE parent = %s AND parenttype = %s",
        (name, doctype),
    )
    return flt((result[0][0] if result else None) or 0.0)


# ---------------------------------------------------------------------------
# Whitelisted API methods
# ---------------------------------------------------------------------------

@frappe.whitelist()
def make_quotation(source_name, target_doc=None):
    if not frappe.has_permission("Event Booking", "read", source_name):
        frappe.throw("You do not have permission to read this Event Booking.")
    if not is_erpnext_installed():
        frappe.throw("ERPNext is required to create a Quotation.")

    def set_missing_values(source, target):
        target.quotation_to = source.party_type
        target.event_booking = source.name
        if source.event_planner:
            target.referral_sales_partner = source.event_planner

    return get_mapped_doc(
        "Event Booking",
        source_name,
        {
            "Event Booking": {
                "doctype": "Quotation",
                "field_map": {
                    "party_name": "party_name",
                    "cost_center": "cost_center",
                },
            }
        },
        target_doc,
        set_missing_values,
    )


@frappe.whitelist()
def convert_lead_and_update_booking(booking_name):
    """Convert the booking's Lead party to a Customer (or link an existing one)
    and repoint the Event Booking to that Customer.

    Called by the "Convert Lead to Customer" button and the lead-conversion
    dialog in event_booking.js.  Returns the shape the client expects::

        {"customer": <customer name>, "already_existed": <bool>}
    """
    if not frappe.has_permission("Event Booking", "write", booking_name):
        frappe.throw(
            _("You do not have permission to modify this Event Booking."),
            frappe.PermissionError,
        )
    if not is_erpnext_installed():
        frappe.throw(_("ERPNext is required to convert a Lead to a Customer."))

    party_type, lead = frappe.db.get_value(
        "Event Booking", booking_name, ["party_type", "party_name"]
    )
    if party_type != "Lead":
        frappe.throw(_("This booking's party is not a Lead."))
    if not lead:
        frappe.throw(_("No Lead is linked to this booking."))

    # Already converted? Reuse the existing Customer linked to this Lead.
    existing = frappe.db.get_value("Customer", {"lead_name": lead}, "name")
    if existing:
        customer_name = existing
        already_existed = True
    else:
        if not frappe.has_permission("Customer", "create"):
            frappe.throw(
                _("You do not have permission to create a Customer."),
                frappe.PermissionError,
            )
        customer_doc = make_customer_from_lead(lead)
        customer_doc.insert(ignore_permissions=True)
        customer_name = customer_doc.name
        already_existed = False

    # Repoint the booking via save() — validate_dates now only guards on
    # event_date changes, so party conversion won't trigger the past-date check.
    booking = frappe.get_doc("Event Booking", booking_name)
    booking.party_type = "Customer"
    booking.party_name = customer_name
    booking.save(ignore_permissions=True)

    return {"customer": customer_name, "already_existed": already_existed}


@frappe.whitelist()
def make_sales_order(source_name, target_doc=None):
    if not frappe.has_permission("Event Booking", "read", source_name):
        frappe.throw(_("You do not have permission to read this Event Booking."))
    if not is_erpnext_installed():
        frappe.throw(_("ERPNext is required to create a Sales Order."))

    booking = frappe.get_doc("Event Booking", source_name)

    # Auto-convert Lead to Customer if needed — Sales Order requires a Customer.
    if booking.party_type == "Lead":
        existing = frappe.db.get_value("Customer", {"lead_name": booking.party_name}, "name")
        if existing:
            customer_name = existing
        else:
            customer_doc = make_customer_from_lead(booking.party_name)
            customer_doc.insert(ignore_permissions=True)
            customer_name = customer_doc.name
        booking.party_type = "Customer"
        booking.party_name = customer_name
        booking.save(ignore_permissions=True)

    if booking.party_type != "Customer":
        frappe.throw(_("Sales Order requires a Customer. Convert the Lead first."))

    def set_missing_values(source, target):
        target.customer = source.party_name
        target.event_booking = source.name
        if source.event_planner:
            target.sales_partner = source.event_planner

    return get_mapped_doc(
        "Event Booking",
        source_name,
        {
            "Event Booking": {
                "doctype": "Sales Order",
                "field_map": {
                    "cost_center": "cost_center",
                    "company": "company",
                },
            }
        },
        target_doc,
        set_missing_values,
    )


@frappe.whitelist()
def make_project(source_name, target_doc=None):
    if not frappe.has_permission("Event Booking", "read", source_name):
        frappe.throw("You do not have permission to read this Event Booking.")
    if not is_erpnext_installed():
        frappe.throw("ERPNext is required to create a Project.")

    def set_missing_values(source, target):
        target.project_name = source.event_name or source.name
        # Project.customer links to ERPNext Customer — only set when applicable.
        target.customer = source.party_name if source.party_type == "Customer" else ""
        target.expected_start_date = source.booking_date or source.event_date
        target.expected_end_date = source.event_date

    return get_mapped_doc(
        "Event Booking",
        source_name,
        {
            "Event Booking": {
                "doctype": "Project",
                "field_map": {
                    "cost_center": "cost_center",
                },
            }
        },
        target_doc,
        set_missing_values,
    )


@frappe.whitelist()
def get_items_from_quotation(quotation_name):
    if not quotation_name:
        return []
    if not frappe.has_permission("Quotation", "read", quotation_name):
        frappe.throw(
            "You do not have permission to read this Quotation.",
            frappe.PermissionError,
        )
    qt = frappe.get_doc("Quotation", quotation_name)
    return [
        {
            "item_code": item.item_code,
            "item_name": item.item_name,
            "qty": item.qty,
            "uom": item.uom,
            "rate": item.rate,
            "amount": item.amount,
        }
        for item in qt.items
    ]


@frappe.whitelist()
def get_items_from_sales_order(sales_order_name):
    if not sales_order_name:
        return []
    if not frappe.has_permission("Sales Order", "read", sales_order_name):
        frappe.throw(
            "You do not have permission to read this Sales Order.",
            frappe.PermissionError,
        )
    so = frappe.get_doc("Sales Order", sales_order_name)
    return [
        {
            "item_code": item.item_code,
            "item_name": item.item_name,
            "qty": item.qty,
            "uom": item.uom,
            "rate": item.rate,
            "amount": item.amount,
        }
        for item in so.items
    ]


@frappe.whitelist(allow_guest=False)
def get_calendar_events(start, end, filters=None):
    import json
    from frappe.utils import add_days

    # Silently fall back to a safe 30-day window on malformed input rather than
    # raising a 500.  The Frappe calendar widget always sends valid ISO dates, so
    # a bad value here means a client bug — returning an empty-but-valid response
    # is preferable to surfacing a traceback.
    try:
        start = getdate(start)
    except Exception:
        start = getdate(today())
    try:
        end = getdate(end)
    except Exception:
        end = getdate(add_days(today(), 30))

    conditions = {"event_date": ("between", [start, end])}
    if filters:
        if isinstance(filters, str):
            filters = json.loads(filters)
        _ALLOWED_FILTERS = {"booking_status", "event_type", "event_planner"}
        if isinstance(filters, dict):
            conditions.update({k: v for k, v in filters.items() if k in _ALLOWED_FILTERS})
        elif isinstance(filters, list):
            for row in filters:
                if isinstance(row, list) and len(row) >= 4 and row[1] in _ALLOWED_FILTERS:
                    conditions[row[1]] = row[3]

    # frappe.get_list respects user permissions; frappe.get_all would bypass them.
    events = frappe.get_list(
        "Event Booking",
        filters=conditions,
        fields=[
            "name", "event_name", "event_date", "event_time",
            "event_end_time", "booking_status", "party_name",
        ],
    )
    out = []
    for ev in events:
        date_str = str(ev.event_date)
        if ev.event_time:
            # Timed event — FullCalendar uses dateTime strings.
            entry = {
                "name": ev.name,
                "title": f"{ev.event_name} ({ev.party_name})",
                "start": f"{date_str} {ev.event_time}",
                "end": f"{date_str} {ev.event_end_time or ev.event_time}",
                "booking_status": ev.booking_status,
                "color": _calendar_color(ev.booking_status),
            }
        else:
            # No time recorded — treat as all-day.  FullCalendar renders
            # all-day events correctly when allDay is True and start/end are
            # plain date strings (no time component).
            entry = {
                "name": ev.name,
                "title": f"{ev.event_name} ({ev.party_name})",
                "start": date_str,
                "end": date_str,
                "allDay": True,
                "booking_status": ev.booking_status,
                "color": _calendar_color(ev.booking_status),
            }
        out.append(entry)
    return out


def _calendar_color(status):
    return {
        "New": "#5e64ff",
        "Quoted": "#5e64ff",
        "Negotiating": "#f4a835",
        "Confirmed": "#2490ef",
        "In Preparation": "#2490ef",
        "Executed": "#adb5bd",
        "Invoiced": "#28a745",
        "Paid": "#28a745",
        "Cancelled": "#e24c4c",
    }.get(status, "#adb5bd")
