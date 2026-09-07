import frappe
from frappe import _

from event_bookings.utils.status import advance_booking_status


def validate_event_booking_link(doc, method=None):
	"""Reject an ``event_booking`` link the user is not entitled to set.

	The status automation deliberately writes to the booking with
	``frappe.db.set_value``: the person submitting an invoice legitimately may
	not own the booking, so requiring write permission there would break the
	whole Phase 1 design. That makes *the link itself* the trust boundary —
	whoever sets it can drive the booking's entire commercial lifecycle.

	``set_value`` bypasses permission_query_conditions, so without this a user
	restricted by a Company User Permission could point their own Sales Invoice
	at a booking in another company — one they cannot even see in a list view —
	and advance it to Paid.

	Only user-supplied values are checked. Links this app sets for itself (see
	the _inherit_event_booking_from_* helpers) carry a flag and are trusted,
	so inheriting a link from a source document never blocks a legitimate save.
	"""
	booking = getattr(doc, "event_booking", None)
	if not booking:
		return

	if getattr(doc.flags, "event_booking_inherited", False):
		return

	# Only validate a value that actually changed on this save.
	if not doc.is_new():
		before = getattr(doc, "get_doc_before_save", lambda: None)()
		if before is not None and getattr(before, "event_booking", None) == booking:
			return

	if not frappe.db.exists("Event Booking", booking):
		return

	if not frappe.has_permission("Event Booking", ptype="read", doc=booking):
		frappe.throw(
			_("You do not have permission to link {0} to this document.").format(booking),
			frappe.PermissionError,
		)

	booking_company = frappe.db.get_value("Event Booking", booking, "company")
	doc_company = getattr(doc, "company", None)
	if booking_company and doc_company and booking_company != doc_company:
		frappe.throw(
			_("Event Booking {0} belongs to {1}, not {2}.").format(
				booking, booking_company, doc_company
			)
		)


def _update_linked_event_booking(doc, callback=None, **field_updates):
	"""Fetch the linked Event Booking and apply field updates.

	Fields are always persisted via frappe.db.set_value first so that the
	link is recorded even if a subsequent full save() is blocked by validation
	(e.g. a stale status-transition check on the draft booking).

	For draft bookings (docstatus=0) a full save() is also attempted so that
	calculate_totals(), version history, and any callback logic fire.  If that
	save fails, the field update is already committed — no data loss.

	For submitted bookings (docstatus=1) only set_value is used (save() is
	not allowed on submitted documents without ignore_permissions).
	"""
	if not getattr(doc, "event_booking", None):
		return

	eb_name = doc.event_booking

	# Step 1 — always persist the field changes immediately.
	try:
		# One UPDATE for the whole set — frappe.db.set_value accepts a dict, and
		# a per-field loop issued a separate statement (and a separate row lock)
		# for each key.
		frappe.db.set_value("Event Booking", eb_name, field_updates, update_modified=False)
	except frappe.DatabaseError:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Failed to update Event Booking {eb_name} fields "
			      f"on {doc.doctype} {doc.name}"
		)
		return

	# Step 2 — recalculate totals (works for both draft and submitted).
	eb = frappe.get_doc("Event Booking", eb_name)

	if eb.docstatus == 0:
		# Draft: full save so calculate_totals, version tracking, and
		# any callback logic fire.
		if callback:
			callback(eb)
		try:
			eb.save()
		except frappe.ValidationError:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Could not recalculate totals on Event Booking {eb_name} "
				      f"after {doc.doctype} {doc.name} — field update is already persisted"
			)
	else:
		# Submitted: use recalculate_totals (db_set, no full save needed)
		try:
			eb.recalculate_totals()
		except Exception:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Could not recalculate totals on submitted Event Booking {eb_name} "
				      f"after {doc.doctype} {doc.name}"
			)


def on_quotation_submit(doc, method):
	_update_linked_event_booking(doc, quotation=doc.name)
	# Official quote sent — ensure the booking has at least reached Quoted
	# (forward-only: a booking already at Invoiced/Confirmed/… is untouched).
	advance_booking_status(
		doc.event_booking, "Quoted", reason=f"Quotation {doc.name} submitted"
	)


def on_quotation_update(doc, method):
	# During a submit, on_update fires BEFORE on_submit. Skip here to avoid
	# doubled work — on_quotation_submit will handle the link + status advance.
	if getattr(doc, "_action", None) == "submit":
		return
	# Keep the reverse link fresh on every save (link set/changed on the source doc).
	if not getattr(doc, "event_booking", None):
		return
	# Skip if the link didn't change — avoids redundant Event Booking saves
	# on no-op Quotation edits. Use getattr for test mocks that lack
	# get_doc_before_save (SimpleNamespace-based test fixtures).
	before = getattr(doc, "get_doc_before_save", lambda: None)()
	if before and getattr(before, "event_booking", None) == doc.event_booking:
		return
	_update_linked_event_booking(doc, quotation=doc.name)
	advance_booking_status(
		doc.event_booking, "Quoted", reason=f"Quotation {doc.name} linked"
	)


def on_sales_order_before_save(doc, method):
	"""Before the Sales Order is saved, inherit the event_booking link from
	the source Quotation if not already set. This ensures the link is
	persisted on the first save (draft), not just on update.

	Only inherits on the first save (``is_new``). Without this guard, a user
	who deliberately clears the ``event_booking`` field would have it
	re-inherited on the next save, silently undoing their change.
	"""
	if doc.is_new() and not getattr(doc, "event_booking", None):
		_inherit_event_booking_from_quotation(doc)


def on_sales_order_submit(doc, method):
	# Link only — per the status matrix a submitted Sales Order does not
	# advance booking status (the deal is already Invoiced/Paid by then).
	_update_linked_event_booking(doc, sales_order=doc.name)


def on_sales_order_update(doc, method):
	# During a submit, on_update fires BEFORE on_submit. Skip here to avoid
	# doubled work — on_sales_order_submit will handle the link + status advance.
	if getattr(doc, "_action", None) == "submit":
		return
	# Inheritance is not repeated here: on_sales_order_before_save already does
	# it on the first save, guarded by is_new() so that clearing the field is
	# respected. Re-inheriting on every save both undid that and re-ran the
	# Quotation lookup for a value before_save had already settled.
	if getattr(doc, "event_booking", None):
		_update_linked_event_booking(doc, sales_order=doc.name)


def _inherit_event_booking_from_quotation(doc):
	"""If the Sales Order has a source quotation that's linked to an Event
	Booking, copy the event_booking reference to this Sales Order.

	This closes the gap where a user creates a Sales Order directly from the
	Quotation (not from the Event Booking form) — the SO should still be
	linked to the same Event Booking.
	"""
	quotation_name = getattr(doc, "quotation", None) or _get_source_quotation(doc)
	if not quotation_name:
		return
	eb = frappe.db.get_value("Quotation", quotation_name, "event_booking")
	if eb and frappe.db.exists("Event Booking", eb):
		doc.event_booking = eb
		# Set by this app from the source document, not typed by a user —
		# validate_event_booking_link trusts it.
		doc.flags.event_booking_inherited = True


def _get_source_quotation(doc):
	"""Resolve the source quotation name from the Sales Order.

	ERPNext stores the originating Quotation in the ``quotation`` field when
	the SO is created via ``make_sales_order``. Some sites use a custom
	field or the Sales Order Item's ``quotation`` reference instead.
	"""
	if getattr(doc, "quotation", None):
		return doc.quotation
	# Fall back: check the first item's quotation reference
	items = getattr(doc, "items", None) or []
	for item in items:
		if getattr(item, "quotation", None):
			return item.quotation
	return None


def on_sales_invoice_submit(doc, method):
	_update_linked_event_booking(doc, sales_invoice=doc.name)
	advance_booking_status(
		doc.event_booking, "Invoiced", reason=f"Sales Invoice {doc.name} submitted"
	)

	# A cash / POS invoice (is_paid = 1) settles at submit and creates no
	# Payment Entry, so the Payment Entry hook never fires for it. on_update
	# cannot catch it either: frappe runs on_update *before* on_submit
	# (run_post_save_methods), and ERPNext computes the Paid status inside its
	# own on_submit — so at on_update time the status is not yet Paid. Re-read
	# it here, after ERPNext has settled it, or such a booking would sit at
	# Invoiced forever.
	_advance_from_settled_invoice(doc.name, f"Sales Invoice {doc.name}")


def on_sales_invoice_before_save(doc, method):
	"""Before the Sales Invoice is saved, inherit the event_booking link from
	the source Sales Order if not already set.

	Only on the first save (``is_new``), matching the Sales Order hook: without
	that guard a user who deliberately clears ``event_booking`` gets it back on
	the next save.
	"""
	if doc.is_new() and not getattr(doc, "event_booking", None):
		_inherit_event_booking_from_sales_order(doc)


def _inherit_event_booking_from_sales_order(doc):
	"""If the Sales Invoice has a source Sales Order that's linked to an
	Event Booking, copy the event_booking reference to this invoice.
	"""
	so_name = getattr(doc, "sales_order", None)
	if not so_name:
		# Fall back: check the first item's sales_order reference
		items = getattr(doc, "items", None) or []
		for item in items:
			if getattr(item, "sales_order", None):
				so_name = item.sales_order
				break
	if not so_name:
		return
	eb = frappe.db.get_value("Sales Order", so_name, "event_booking")
	if eb and frappe.db.exists("Event Booking", eb):
		doc.event_booking = eb
		doc.flags.event_booking_inherited = True


def on_sales_invoice_update(doc, method):
	# During a submit, on_update fires BEFORE on_submit. Skip here to avoid
	# doubled work — on_sales_invoice_submit will handle the link + status advance.
	if getattr(doc, "_action", None) == "submit":
		return
	# See on_sales_order_update: inheritance happens once, in before_save.
	if not getattr(doc, "event_booking", None):
		return
	_update_linked_event_booking(doc, sales_invoice=doc.name)
	if doc.docstatus == 1:
		si_status = getattr(doc, "status", None)
		# Partly paid → Confirmed (deposit received, event is confirmed)
		if si_status in ("Partly Paid", "Partly Paid and Discounted"):
			advance_booking_status(
				doc.event_booking, "Confirmed",
				reason=f"Sales Invoice {doc.name} partly paid"
			)
		# Fully paid → Paid
		elif si_status in ("Paid",):
			advance_booking_status(
				doc.event_booking, "Paid",
				reason=f"Sales Invoice {doc.name} fully paid"
			)


def on_quotation_cancel(doc, method):
	_update_linked_event_booking(doc, quotation=None)


def on_sales_order_cancel(doc, method):
	_update_linked_event_booking(doc, sales_order=None)


def on_sales_invoice_cancel(doc, method):
	_update_linked_event_booking(doc, sales_invoice=None)


def on_payment_entry_submit(doc, method):
	"""When a Payment Entry is submitted, ERPNext updates the linked Sales
	Invoice's status via db_set (not save), so the SI's on_update hook
	doesn't fire. This hook re-checks the linked SI's status and advances
	the booking status accordingly.

	Safety: only acts on references that have an event_booking link.
	Payments against SIs/SOs with no Event Booking are untouched.
	"""
	for ref in (doc.references or []):
		ref_doctype = getattr(ref, "reference_doctype", None)
		ref_name = getattr(ref, "reference_name", None)
		if not ref_doctype or not ref_name:
			continue

		try:
			if ref_doctype == "Sales Invoice":
				_eb_advance_from_sales_invoice(doc.name, ref_name)
			# Sales Order direct payments (advance payments before invoicing)
			# don't change booking status — the booking advances when the SI
			# is submitted (→ Invoiced) and when the SI is paid (→ Confirmed/Paid).
			# SO advance payments are just a deposit, not a status trigger.
		except Exception:
			frappe.log_error(
				message=(
					f"Payment Entry: {doc.name}\n"
					f"Reference: {ref_doctype} {ref_name}\n\n"
					f"{frappe.get_traceback()}"
				),
				title="Event Bookings: payment status sync failed",
			)


def _advance_from_settled_invoice(si_name, reason_prefix):
	"""Advance a booking from a Sales Invoice's *current* payment status.

	Shared by every route that settles an invoice: Payment Entry, Journal
	Entry, and a cash invoice that submits already paid. Forward-only —
	advance_booking_status refuses to move a booking backwards.
	"""
	# Both columns in one read. This was two get_value calls against the same
	# row, plus an exists() probe that advance_booking_status already performs
	# for itself (it is a documented no-op when the booking is missing).
	si = frappe.db.get_value(
		"Sales Invoice", si_name, ["event_booking", "status"], as_dict=True
	)
	if not si or not si.event_booking:
		return

	status = si.status
	if status in ("Partly Paid", "Partly Paid and Discounted"):
		advance_booking_status(
			si.event_booking, "Confirmed", reason=f"{reason_prefix} partly paid"
		)
	elif status == "Paid":
		advance_booking_status(
			si.event_booking, "Paid", reason=f"{reason_prefix} fully paid"
		)


def on_journal_entry_submit(doc, method):
	"""Journal Entries settle invoices too, and create no Payment Entry.

	Without this, an invoice paid by journal never advances its booking past
	Invoiced. Exception-safe: an accounting entry must never fail because of
	this app.
	"""
	for ref in (doc.accounts or []):
		if getattr(ref, "reference_type", None) != "Sales Invoice":
			continue
		si_name = getattr(ref, "reference_name", None)
		if not si_name:
			continue
		try:
			si = frappe.get_doc("Sales Invoice", si_name)
			si.set_status(update=True, update_modified=False)
			_advance_from_settled_invoice(si_name, f"Journal Entry {doc.name} — Sales Invoice {si_name}")
		except Exception:
			frappe.log_error(
				message=(
					f"Journal Entry: {doc.name}\n"
					f"Sales Invoice: {si_name}\n\n"
					f"{frappe.get_traceback()}"
				),
				title="Event Bookings: journal payment sync failed",
			)


def _eb_advance_from_sales_invoice(pe_name, si_name):
	"""Re-check a Sales Invoice's payment status after a Payment Entry is
	submitted and advance the linked Event Booking if the SI has one.
	"""
	eb = frappe.db.get_value("Sales Invoice", si_name, "event_booking")
	if not eb:
		return
	if not frappe.db.exists("Event Booking", eb):
		return

	si = frappe.get_doc("Sales Invoice", si_name)
	# `update=True` is the real keyword — `update_status` raised TypeError on
	# every call, and the bare except below swallowed it, so this hook never
	# once advanced a booking. set_status(update=True) writes the column
	# itself, so no follow-up db_set is needed.
	si.set_status(update=True, update_modified=False)

	# Read status off the in-memory doc rather than re-querying: set_status
	# assigns self.status before writing the row, so the object is authoritative.
	if si.status in ("Partly Paid", "Partly Paid and Discounted"):
		advance_booking_status(
			eb, "Confirmed",
			reason=f"Payment Entry {pe_name} — Sales Invoice {si_name} partly paid"
		)
	elif si.status == "Paid":
		advance_booking_status(
			eb, "Paid",
			reason=f"Payment Entry {pe_name} — Sales Invoice {si_name} fully paid"
		)


def on_accounting_dimension_update(doc, method):
	"""When the Event Booking Accounting Dimension is saved, Frappe recreates
	event_booking custom fields on all accounting doctypes. This hook re-runs
	the cleanup to delete fields from irrelevant doctypes and reposition the
	ones we keep. Only fires for the Event Booking dimension.
	"""
	if doc.document_type != "Event Booking":
		return
	try:
		from event_bookings.install import _cleanup_event_booking_fields
		_cleanup_event_booking_fields()
	except Exception:
		frappe.log_error(title="Failed to cleanup event_booking fields after AD update", message=frappe.get_traceback())


def on_shift_assignment_update(doc, method=None):
	"""Recompute per-designation ``qty_assigned`` on the linked booking's staff
	requirements whenever a Shift Assignment tied to it changes.

	Counts submitted Shift Assignments for the booking, matching the assigned
	Employee's designation to each Event Staff Requirement row.  Safe no-op when
	the Shift Assignment carries no ``event_booking`` link (field absent → None).

	On ``on_trash`` the row still exists in the DB, so it must be explicitly
	excluded from the count — otherwise the count would still include it.
	"""
	booking = getattr(doc, "event_booking", None)
	if not booking:
		return

	params = {"booking": booking}
	exclude_clause = ""
	if method == "on_trash":
		# The trashed row is still in the DB at this point — exclude it.
		params["exclude_name"] = doc.name
		exclude_clause = "AND sa.name != %(exclude_name)s"

	frappe.db.sql(
		f"""
		UPDATE `tabEvent Staff Requirement` esr
		SET esr.qty_assigned = (
			SELECT COUNT(*)
			FROM `tabShift Assignment` sa
			INNER JOIN `tabEmployee` emp ON emp.name = sa.employee
			WHERE sa.event_booking = %(booking)s
			  AND sa.docstatus = 1
			  {exclude_clause}
			  AND emp.designation = esr.designation
		)
		WHERE esr.parent = %(booking)s
		  AND esr.parenttype = 'Event Booking'
		""",
		params,
	)
