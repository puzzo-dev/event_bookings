import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils import today, getdate, flt
from frappe.utils.data import escape_html

from event_bookings.utils.erpnext_bridge import is_erpnext_installed, make_customer_from_lead
from event_bookings.utils.status import CANCELLED


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
        self._fetch_contact_phone()
        # Quotation-first flow: new bookings always carry a Customer
        # (legacy rows are exempt — the party model is retired, not frozen).
        if self.is_new() and not self.customer:
            frappe.throw(
                "Customer is required — an Event Booking is created from an "
                "accepted Quotation (Quotation → Create → Event Booking)."
            )

    def before_save(self):
        self.calculate_totals()
        # Idempotent and cheap: only writes a blank field, so it is safe to run
        # on every save. Must NOT be gated on has_status_changed() — that is
        # False when a booking is *created* already Confirmed or Cancelled.
        self.stamp_lifecycle_dates()
        # has_status_changed() fetches and caches old_status once.
        # _validate_status_transition() reuses the cache — avoids a second DB hit.
        if self.has_status_changed():
            self._validate_status_transition()
            self.handle_status_transition()

    def before_update_after_submit(self):
        """Frappe runs a different hook chain once a document is submitted.

        For docstatus 1, run_before_save_methods() dispatches on
        _action == "update_after_submit" and runs ONLY this method — neither
        validate nor before_save fires (frappe/model/document.py). booking_status
        is allow_on_submit, so it keeps changing after submit; without this the
        entire status-transition chain was dead on submitted bookings:
        lifecycle dates were never stamped, staffing alerts never sent, and a
        status-based cancellation never cascaded to the linked Quotation /
        Sales Order / Sales Invoice.
        """
        self.stamp_lifecycle_dates()
        if self.has_status_changed():
            # Validated here too. before_save never runs on a submitted
            # document, so a guard placed only there governs exactly the path
            # that does not need it — and leaves the submitted path, the one
            # that can cancel linked documents while staying submitted,
            # unchecked.
            self._validate_status_transition()
            self.handle_status_transition()

    def after_insert(self):
        """Quotation-first: write the reverse link on the source Quotation so
        its Connections tab lights up and on_quotation_update keeps totals
        fresh. One booking per quotation — never overwrite an existing link."""
        if self.quotation:
            # One read, not two: get_value returns None both when the Quotation
            # is missing and when its event_booking is empty, and set_value on a
            # row that does not exist is a no-op — so the separate exists()
            # probe added a query without changing any outcome.
            existing = frappe.db.get_value("Quotation", self.quotation, "event_booking")
            if not existing:
                frappe.db.set_value(
                    "Quotation", self.quotation, "event_booking", self.name,
                    update_modified=False,
                )

    def before_cancel(self):
        # Cancel linked submitted documents SYNCHRONOUSLY, before the
        # docstatus flip: Frappe's back-link check (check_no_back_links_exist)
        # runs after on_cancel and raises LinkExistsError while any submitted
        # Quotation/Sales Order/Sales Invoice/Stock Entry still references
        # this booking. The status-based Cancelled flow (no docstatus change)
        # keeps the background-enqueued cascade instead.
        _cancel_linked_documents(self.name)

    def on_cancel(self):
        # Linked documents were already cancelled in before_cancel.
        #
        # Keep the two cancellation concepts in agreement. ERPNext derives
        # status from docstatus — see erpnext/controllers/status_updater.py,
        # ["Cancelled", "eval:self.docstatus==2"] — so a cancelled document can
        # never read as anything else. This app also has a status-only cancel
        # (no docstatus change) for draft bookings, which left docstatus-2
        # bookings sitting at booking_status "Confirmed" with no cancelled_on:
        # they stayed "converted" in every report and chart forever.
        #
        # Set the values in-memory BEFORE writing, so doc_events hooks (e.g.
        # Google Calendar sync on on_cancel) see the cancelled status —
        # db_set writes the row but does not update the in-memory object.
        #
        # Both columns go out in one statement: db_set accepts a dict, and two
        # calls meant two UPDATEs and two row locks for a single state change.
        updates = {"booking_status": CANCELLED}
        self.booking_status = CANCELLED
        if not self.cancelled_on:
            self.cancelled_on = frappe.utils.today()
            updates["cancelled_on"] = self.cancelled_on
        self.db_set(updates, update_modified=False)

    def _validate_status_transition(self):
        if self.is_new():
            return
        old_status = self._cached_old_status
        if old_status is None or old_status == self.booking_status:
            return

        # Status transitions are otherwise unrestricted; validation still runs
        # so the transition hook (notifications, linked-doc cancellation) fires
        # reliably.
        #
        # The exception is cancelling a *submitted* booking by status alone.
        # booking_status is allow_on_submit, so that path ran the whole
        # cancellation cascade — linked Quotation, Sales Order and Sales Invoice
        # all cancelled — while docstatus stayed 1. The booking then read as
        # cancelled everywhere this app looks and as live everywhere ERPNext
        # does, and it could still be amended and submitted against.
        #
        # The status-only cancel is deliberate for drafts, where there is no
        # submitted document to cancel (see on_cancel). On a submitted booking
        # the two concepts have to agree, and Cancel is what makes them agree:
        # on_cancel sets booking_status itself.
        if (
            self.booking_status == CANCELLED
            and self.docstatus == 1
            and getattr(self, "_action", None) != "cancel"
        ):
            frappe.throw(
                _(
                    "Use Cancel to cancel a submitted booking. Setting the status "
                    "to Cancelled on its own would cancel the linked documents "
                    "while leaving this booking submitted."
                ),
                title=_("Cancel the Booking Instead"),
            )

    # -----------------------------------------------------------------
    # Validations
    # -----------------------------------------------------------------

    def calculate_totals(self):
        """
        Sum line-item amounts from linked documents via SQL aggregation.
        Avoids loading full Document objects (and child tables) inside validate.

        - total_estimated: Quotation items total (the original quote)
        - total_actual: Sales Invoice grand_total if linked (the actual
          invoiced amount including taxes), otherwise Sales Order items total
          (the agreed amount, which may include items added after quoting)
        """
        self.total_estimated = _sql_items_total("Quotation", self.quotation)
        if self.sales_invoice:
            # Use the SI grand_total — the actual invoiced amount (items + taxes + shipping)
            si_total = frappe.db.get_value("Sales Invoice", self.sales_invoice, "grand_total")
            self.total_actual = flt(si_total or 0.0)
        elif self.sales_order:
            # No invoice yet — use the SO items total
            self.total_actual = _sql_items_total("Sales Order", self.sales_order)
        else:
            self.total_actual = 0.0

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

    def _fetch_contact_phone(self):
        """Fill Contact Phone from whoever the booking is for.

        The number is what a reminder or a confirmation is actually sent to, and
        it lives on the Lead or on the Customer's primary Contact — not on the
        booking. Read-only and refreshed on every save, so it follows the
        contact record rather than going stale the moment someone updates it
        there.

        The Customer link is preferred over party_type: a booking that started
        as a Lead carries the Customer once the quotation is accepted, and that
        Contact is the more current of the two.
        """
        customer = self.customer or (self.party_name if self.party_type == "Customer" else None)

        if customer:
            self.contact_phone = self._primary_contact_phone(customer)
            return

        if self.party_type == "Lead" and self.party_name:
            self.contact_phone = (
                frappe.db.get_value("Lead", self.party_name, "whatsapp_no")
                or frappe.db.get_value("Lead", self.party_name, "mobile_no")
                or frappe.db.get_value("Lead", self.party_name, "phone")
            )
            return

        self.contact_phone = None

    @staticmethod
    def _primary_contact_phone(customer):
        """The phone on the Customer's first linked Contact, if there is one."""
        contact = frappe.get_all(
            "Dynamic Link",
            filters={
                "link_doctype": "Customer",
                "link_name": customer,
                "parenttype": "Contact",
            },
            pluck="parent",
            order_by="idx asc",
            limit=1,
        )
        if not contact:
            return None
        return frappe.db.get_value("Contact", contact[0], "mobile_no") or frappe.db.get_value(
            "Contact", contact[0], "phone"
        )

    def validate_dates(self):
        """
        Past-date guard — tolerant of legacy/back-dated bookings.

        - New bookings may be back-dated (recording events that already ran).
        - An existing booking cannot be MOVED to a past date.
        - An existing booking whose event date is already past saves, submits
          and cancels freely — submit/cancel run the full validate chain, so
          a stricter guard would freeze historical bookings (P1-7).
        """
        if not self.event_date or getdate(self.event_date) >= getdate(today()):
            return
        if not self.name:
            return  # new, unsaved document — back-dating allowed
        # One read: a document that is not yet in the table returns None here,
        # which is exactly the "new, back-dating allowed" case the exists()
        # probe was checking for.
        stored = frappe.db.get_value("Event Booking", self.name, "event_date")
        if stored and getdate(stored) != getdate(self.event_date):
            frappe.throw("Event Date cannot be moved to a past date on an existing booking.")

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

        if status == "Confirmed":
            self._notify_staff_requirements()

        elif status == "Cancelled":
            self.cancel_linked_documents()

    def stamp_lifecycle_dates(self):
        """Record when a booking converted and when it was lost.

        Analytics previously dated both events by ``modified``, which is the
        last edit of *anything* on the booking — so an unrelated edit silently
        re-dated a historical conversion or loss into the current period.
        These two fields are written once and never moved.

        ``confirmed_on`` is stamped on reaching Confirmed *or any later state*,
        because a booking can jump straight from Invoiced to Paid and never
        pass through Confirmed itself.
        """
        from event_bookings.utils.status import STATUS_ORDER, status_index

        today = frappe.utils.today()
        confirmed_idx = STATUS_ORDER.index("Confirmed")
        current_idx = status_index(self.booking_status)

        if current_idx is not None and current_idx >= confirmed_idx and not self.confirmed_on:
            self.confirmed_on = today

        if self.booking_status == CANCELLED and not self.cancelled_on:
            self.cancelled_on = today

    def _notify_staff_requirements(self):
        """
        When moving to Confirmed, alert managers about outstanding staffing gaps.

        HRMS Shift Assignment requires a named employee on every record and does not
        support unassigned placeholder slots.  Managers must create Shift Assignments
        manually via HR > Shift Assignment with event_booking set to this booking.
        """
        needed = []
        for req in self.get("staff_requirements") or []:
            gap = int(req.get("qty_required") or 0) - int(req.get("qty_assigned") or 0)
            if gap > 0:
                needed.append(
                    f"{escape_html(str(req.get('designation') or ''))}: "
                    f"{gap} slot(s) required"
                )
        if needed:
            frappe.msgprint(
                "<b>Staff requirements outstanding.</b><br>"
                "Please create Shift Assignments in <b>HR &gt; Shift Assignment</b> "
                f"with the <i>Event Booking</i> field set to <b>{escape_html(self.name)}</b>:<ul>"
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
            # v15 API: frappe.in_test is v16+. On v15 this raised
            # AttributeError, so cancelling any booking crashed the save.
            now=frappe.flags.in_test,
            # The worker reads this booking's state to decide what to cancel.
            # Without this it can start before the cancelling transaction has
            # committed and read the pre-cancel row — or not find it at all.
            # Ignored when now=True, so tests still run inline.
            enqueue_after_commit=True,
        )

    # -----------------------------------------------------------------
    # Document Creation Helpers
    # -----------------------------------------------------------------

    # -----------------------------------------------------------------
    # Utilities
    # -----------------------------------------------------------------

    def get_settings(self):
        return frappe.get_cached_doc("Event Booking Settings")

    @staticmethod
    def get_indicator(doc):
        """Return colored indicator for booking_status in list views.

        Colors follow the status order (commercial → operational):
        deal phases blue/orange, money pending orange, paid green,
        event phases blue, executed grey, cancelled red.
        """
        status_colors = {
            "New": "blue",
            "Quoted": "blue",
            "Invoiced": "orange",
            "Confirmed": "blue",
            "Paid": "green",
            "Executed": "gray",
            "Cancelled": "red",
        }
        return [doc.booking_status, status_colors.get(doc.booking_status, "gray")]


# ---------------------------------------------------------------------------
# Linked-document cancellation cascade
# ---------------------------------------------------------------------------

def _cancel_linked_documents_background(booking_name):
    """
    Background worker entry point (enqueued by cancel_linked_documents for the
    status-based Cancelled flow) — delegates to the synchronous core.
    """
    _cancel_linked_documents(booking_name)


def _cancel_linked_documents(booking_name):
    """
    Cancel submitted documents linked to an Event Booking (synchronous core).

    Shared by:
    - before_cancel (docstatus cancel) — MUST complete before Frappe's
      back-link check runs, so the cancel is not blocked by submitted
      Quotation / Sales Order / Sales Invoice / Stock Entry references;
    - the background worker (status-based Cancelled on draft/submitted
      bookings) so user-facing saves never block on ERPNext ledger work.

    Each cancellation is permission-checked and individually error-logged —
    one failure never aborts the rest. If a submitted link survives (missing
    permission or a cancel error), Frappe's back-link check stops the booking
    cancel with a LinkExistsError naming the blocking document.
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
    if frappe.db.exists("DocType", "Stock Entry"):
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
    if frappe.db.exists("DocType", "Shift Assignment"):
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
def make_event_booking(source_name, target_doc=None):
    """Create an Event Booking FROM an accepted Quotation.

    The quotation-first flow (user-confirmed): a booking only exists after a
    quotation is accepted. Called by the Quotation form's
    Create → Event Booking button via frappe.model.open_mapped_doc.

    Customer resolution:
    - quotation_to == "Customer" → customer = party_name
    - quotation_to == "Lead"     → convert via make_customer_from_lead
                                    (reuses an existing Customer when the
                                    lead was already converted)
    """
    if not frappe.has_permission("Quotation", "read", source_name):
        frappe.throw(
            "You do not have permission to read this Quotation.",
            frappe.PermissionError,
        )
    if not frappe.has_permission("Event Booking", "create"):
        frappe.throw(
            "You do not have permission to create an Event Booking.",
            frappe.PermissionError,
        )
    if not is_erpnext_installed():
        frappe.throw("ERPNext is required to create an Event Booking from a Quotation.")

    quotation = frappe.get_doc("Quotation", source_name)

    # Lock the Quotation row to serialize concurrent make_event_booking calls.
    # Without this, two requests can both pass the duplicate check below and
    # both create bookings for the same Quotation.
    frappe.db.get_value("Quotation", source_name, "name", for_update=True)

    # Event Booking can only be created from a submitted Quotation —
    # same pattern as Quotation → Sales Order in ERPNext.
    if quotation.docstatus != 1:
        frappe.throw(
            "Event Booking can only be created from a submitted Quotation. "
            f"Quotation {source_name} is {'draft' if quotation.docstatus == 0 else 'cancelled'}.",
            frappe.ValidationError,
        )

    # Block creation from expired quotations — same as ERPNext's
    # make_sales_order check against Selling Settings.
    from frappe.utils import getdate, nowdate
    valid_till = quotation.get("valid_till")
    if valid_till and getdate(valid_till) < getdate(nowdate()):
        frappe.throw(
            f"Validity period of Quotation {source_name} has ended. "
            "Cannot create an Event Booking from an expired quotation.",
            frappe.ValidationError,
        )

    # One Event Booking per Quotation — prevent duplicates.
    existing = frappe.db.get_value("Event Booking", {"quotation": source_name, "docstatus": ("<", 2)})
    if existing:
        frappe.throw(
            f"Quotation {source_name} already has an Event Booking ({existing}). "
            "One booking per quotation.",
            frappe.ValidationError,
        )

    customer = _resolve_customer_from_quotation(quotation)

    def set_missing_values(source, target):
        target.customer = customer
        # Booking status starts at Quoted — a quotation exists and was
        # accepted (decided with the status-order redesign).
        target.booking_status = "Quoted"
        # Read-only field, set server-side; on_quotation_update keeps it fresh.
        target.quotation = source.name

    return get_mapped_doc(
        "Quotation",
        source_name,
        {
            "Quotation": {
                "doctype": "Event Booking",
                "field_map": {
                    "company": "company",
                },
            }
        },
        target_doc,
        set_missing_values,
    )


def _resolve_customer_from_quotation(quotation):
    """Resolve the Customer for a quotation→booking mapping.

    Lead quotations are converted (reusing an existing Customer linked to the
    lead) — bookings always carry a Customer under the quotation-first model.
    """
    party_type = quotation.quotation_to
    party = quotation.party_name
    if not party:
        frappe.throw("The quotation has no party linked.")

    if party_type == "Customer":
        return party

    if party_type == "Lead":
        if not frappe.has_permission("Customer", "create"):
            frappe.throw(
                _("You do not have permission to create a Customer."),
                frappe.PermissionError,
            )
        existing = frappe.db.get_value("Customer", {"lead_name": party}, "name")
        if existing:
            return existing
        customer_doc = make_customer_from_lead(party)
        customer_doc.insert(ignore_permissions=True)
        return customer_doc.name

    frappe.throw(
        f"Quotation party type '{party_type}' cannot be linked to an Event "
        "Booking. Convert the party to a Customer first."
    )


@frappe.whitelist()
def make_sales_order(source_name, target_doc=None):
    """Create a Sales Order from an Event Booking.

    Works with or without a linked Quotation:
    - If a Quotation is linked, items are copied from it (via ERPNext's
      quotation.make_sales_order mapping).
    - If no Quotation exists, a blank Sales Order is created with the
      customer / company / cost_center from the Event Booking.

    The Sales Order's ``event_booking`` custom field is set so the
    ERPNext doc_events can link it back.
    """
    if not frappe.has_permission("Event Booking", "read", source_name):
        frappe.throw("You do not have permission to read this Event Booking.")
    if not frappe.has_permission("Sales Order", "create"):
        frappe.throw(
            "You do not have permission to create a Sales Order.",
            frappe.PermissionError,
        )
    if not is_erpnext_installed():
        frappe.throw("ERPNext is required to create a Sales Order.")

    source = frappe.get_doc("Event Booking", source_name)

    # If a quotation is linked, use ERPNext's mapping to copy items.
    if source.quotation and frappe.db.exists("Quotation", source.quotation):
        from erpnext.selling.doctype.quotation.quotation import make_sales_order as _qtn_make_so

        target = _qtn_make_so(source.quotation, target_doc=target_doc)
    else:
        # No quotation — create a blank Sales Order from the booking.
        target = frappe.new_doc("Sales Order")

    def set_missing_values(source, target):
        target.customer = source.customer or target.customer
        target.company = source.company or target.company
        if source.cost_center:
            target.cost_center = source.cost_center
        target.event_booking = source.name
        # Delivery date = event date if set
        if source.event_date:
            target.delivery_date = source.event_date

    set_missing_values(source, target)
    return target


@frappe.whitelist()
def make_project(source_name, target_doc=None):
    if not frappe.has_permission("Event Booking", "read", source_name):
        frappe.throw("You do not have permission to read this Event Booking.")
    if not frappe.has_permission("Project", "create"):
        frappe.throw(
            "You do not have permission to create a Project.",
            frappe.PermissionError,
        )
    if not is_erpnext_installed():
        frappe.throw("ERPNext is required to create a Project.")

    def set_missing_values(source, target):
        target.project_name = source.event_name or source.name
        target.customer = source.customer or ""
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
def make_stock_entry(booking_name, stock_entry_type="Material Issue"):
    """Create a new Stock Entry linked to an Event Booking (unsaved — opened in form).

    Prefills event_booking, company, cost_center from the booking, and
    source/target warehouses from Event Booking Settings.default_warehouse.
    Returns the new doc dict so frappe.model.open_mapped_doc can open it.
    """
    # write, not read: the entry this opens carries an event_booking link, and
    # setting that link is what drives the booking's Items Used and its status
    # automation. validate_event_booking_link refuses it on save without write,
    # so checking read here only sent the user to a form that could not be
    # saved.
    if not frappe.has_permission("Event Booking", "write", booking_name):
        frappe.throw(
            "You do not have permission to change this Event Booking.",
            frappe.PermissionError,
        )
    if not is_erpnext_installed():
        frappe.throw("ERPNext is required to create a Stock Entry.")
    if not frappe.has_permission("Stock Entry", "create"):
        frappe.throw(
            "You do not have permission to create a Stock Entry.",
            frappe.PermissionError,
        )

    # The type comes from the caller. An unknown one fails on save with a link
    # error from deep inside ERPNext; refusing it here says what is wrong.
    stock_entry_type = str(stock_entry_type or "").strip()
    if not frappe.db.exists("Stock Entry Type", stock_entry_type):
        frappe.throw(f"{stock_entry_type or 'Stock Entry Type'} is not a Stock Entry Type.")

    booking = frappe.get_doc("Event Booking", booking_name)

    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = stock_entry_type
    se.company = booking.company or frappe.defaults.get_user_default("Company")
    se.event_booking = booking.name
    if booking.cost_center:
        se.cost_center = booking.cost_center

    # Prefill the warehouse the purpose actually has.
    #
    # Both sides used to get the same warehouse whatever the purpose, which is
    # wrong in two different ways: a Material Issue has no target at all, and a
    # Material Transfer with source equal to target is refused by ERPNext. The
    # prefill was producing an entry the user had to correct before it would
    # save.
    default_warehouse = _get_settings_default_warehouse()
    if default_warehouse:
        purpose = frappe.db.get_value("Stock Entry Type", stock_entry_type, "purpose")
        if purpose == "Material Receipt":
            se.to_warehouse = default_warehouse
        else:
            # Issue, Transfer and the rest all draw from somewhere; a transfer's
            # destination is the choice the user is here to make.
            se.from_warehouse = default_warehouse

    return se.as_dict()


def _get_settings_default_warehouse():
    """Read default_warehouse from Event Booking Settings (Single)."""
    try:
        return frappe.db.get_value("Event Booking Settings", None, "default_warehouse")
    except Exception:
        return None


@frappe.whitelist()
def get_items_from_quotation(quotation_name):
    if not quotation_name:
        return []
    if not frappe.has_permission("Quotation", "read", quotation_name):
        frappe.throw(
            "You do not have permission to read this Quotation.",
            frappe.PermissionError,
        )
    # get_all on the child table, not get_doc on the parent: get_doc loads the
    # Quotation plus every one of its child tables (taxes, payment schedule,
    # pricing rules) to read one of them. Permission was already checked above,
    # against the parent, which is where it belongs.
    return frappe.get_all(
        "Quotation Item",
        filters={"parent": quotation_name, "parenttype": "Quotation"},
        fields=["item_code", "item_name", "qty", "uom", "rate", "amount"],
        order_by="idx asc",
        limit_page_length=0,
    )


@frappe.whitelist()
def get_items_from_sales_order(sales_order_name):
    if not sales_order_name:
        return []
    if not frappe.has_permission("Sales Order", "read", sales_order_name):
        frappe.throw(
            "You do not have permission to read this Sales Order.",
            frappe.PermissionError,
        )
    # Child-table read — see get_items_from_quotation for the rationale.
    return frappe.get_all(
        "Sales Order Item",
        filters={"parent": sales_order_name, "parenttype": "Sales Order"},
        fields=["item_code", "item_name", "qty", "uom", "rate", "amount"],
        order_by="idx asc",
        limit_page_length=0,
    )


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
        # Whitelist filter keys — prevents arbitrary filter injection from the client.
        #
        # And coerce the values. The keys were checked and the values passed
        # through untouched, so a client could send an operator form —
        # ["!=", "Cancelled"], ["like", "%"] — and choose the comparison as well
        # as the term. get_list still applies the row-level partition, so this
        # leaked nothing, but the calendar is an equality filter and letting the
        # client pick the operator is surface with no purpose.
        _ALLOWED_FILTERS = {"booking_status", "event_type", "event_planner"}
        conditions.update({
            k: str(v)
            for k, v in filters.items()
            if k in _ALLOWED_FILTERS and isinstance(v, (str, int, float))
        })

    # frappe.get_list respects user permissions; frappe.get_all would bypass them.
    events = frappe.get_list(
        "Event Booking",
        filters=conditions,
        fields=[
            "name", "event_name", "event_date", "event_time",
            "event_end_time", "booking_status", "customer",
        ],
    )

    # Batch-resolve customer display names for calendar titles.
    customer_names = list({ev.customer for ev in events if ev.customer})
    customer_display = (
        dict(frappe.get_all(
            "Customer",
            filters={"name": ("in", customer_names)},
            fields=["name", "customer_name"],
            as_list=1,
            limit_page_length=0,
        ))
        if customer_names else {}
    )

    out = []
    for ev in events:
        party = customer_display.get(ev.customer) or ev.customer or ""
        title = f"{ev.event_name} ({party})" if party else ev.event_name
        date_str = str(ev.event_date)
        if ev.event_time:
            # Timed event — FullCalendar uses dateTime strings.
            entry = {
                "name": ev.name,
                "title": title,
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
                "title": title,
                "start": date_str,
                "end": date_str,
                "allDay": True,
                "booking_status": ev.booking_status,
                "color": _calendar_color(ev.booking_status),
            }
        out.append(entry)
    return out


def _calendar_color(status):
    """Calendar event colors — same semantics as get_indicator."""
    return {
        "New": "#5e64ff",
        "Quoted": "#5e64ff",
        "Invoiced": "#f4a835",
        "Confirmed": "#2490ef",
        "Paid": "#28a745",
        "Executed": "#adb5bd",
        "Cancelled": "#e24c4c",
    }.get(status, "#adb5bd")


def on_doctype_update():
    """Indexes for the columns the reports, hooks and partition filter on.

    Declared here as the source of truth; patches/index_hot_columns covers the
    ERPNext-owned tables and sites where this hook does not fire.
    """
    # booking_status, event_date, company, customer and sales_invoice carry
    # search_index on the field, so Frappe already indexes them.
    frappe.db.add_index("Event Booking", ["event_planner"])
    frappe.db.add_index("Event Booking", ["quotation"])
    frappe.db.add_index("Event Booking", ["sales_order"])
