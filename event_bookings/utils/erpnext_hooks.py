import frappe

from event_bookings.utils.erpnext_bridge import default_non_group


def on_customer_before_insert(doc, method=None):
	"""Fill blank Customer Group / Territory so auto-created Customers insert cleanly.

	ERPNext creates a Customer implicitly whenever a Lead-addressed Quotation is
	converted to a Sales Order or Sales Invoice
	(``selling/doctype/quotation/quotation.py::_make_customer``).  If the site
	makes customer_group or territory mandatory — commonly via a Property Setter
	— and the Lead supplies neither, that insert raises MandatoryError and
	ERPNext surfaces a blocking "Mandatory Missing" dialog telling the user to go
	create the Customer by hand.  That dialog is the lead-conversion popup we
	want gone: the conversion is supposed to be silent.

	Only ever fills blanks, so an explicit choice on the form is never overridden.
	"""
	if not doc.get("customer_group"):
		doc.customer_group = default_non_group("Customer Group", "customer_group")
	if not doc.get("territory"):
		doc.territory = default_non_group("Territory", "territory")


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
		for field, value in field_updates.items():
			frappe.db.set_value("Event Booking", eb_name, field, value, update_modified=False)
	except frappe.DatabaseError:
		frappe.log_error(
			title=f"Failed to update Event Booking {eb_name} fields "
			      f"on {doc.doctype} {doc.name}"
		)
		return

	# Step 2 — for draft bookings, also run a full save so that
	# calculate_totals, version tracking, and any callback logic fire.
	eb = frappe.get_doc("Event Booking", eb_name)
	if eb.docstatus != 0:
		return

	if callback:
		callback(eb)

	try:
		eb.save()
	except frappe.ValidationError:
		frappe.log_error(
			title=f"Could not recalculate totals on Event Booking {eb_name} "
			      f"after {doc.doctype} {doc.name} — field update is already persisted"
		)


def on_quotation_submit(doc, method):
	_update_linked_event_booking(doc, quotation=doc.name)


def on_quotation_update(doc, method):
	# Keep the reverse link fresh on every save (link set/changed on the source doc).
	if getattr(doc, "event_booking", None):
		_update_linked_event_booking(doc, quotation=doc.name)


def on_sales_order_submit(doc, method):
	_update_linked_event_booking(doc, sales_order=doc.name)


def on_sales_order_update(doc, method):
	if getattr(doc, "event_booking", None):
		_update_linked_event_booking(doc, sales_order=doc.name)


def on_sales_invoice_submit(doc, method):
	_update_linked_event_booking(doc, sales_invoice=doc.name)


def on_sales_invoice_update(doc, method):
	if getattr(doc, "event_booking", None):
		_update_linked_event_booking(doc, sales_invoice=doc.name)


def on_quotation_cancel(doc, method):
	_update_linked_event_booking(doc, quotation=None)


def on_sales_order_cancel(doc, method):
	_update_linked_event_booking(doc, sales_order=None)


def on_sales_invoice_cancel(doc, method):
	_update_linked_event_booking(doc, sales_invoice=None)


def on_shift_assignment_update(doc, method):
	"""Recompute per-designation ``qty_assigned`` on the linked booking's staff
	requirements whenever a Shift Assignment tied to it changes.

	Counts submitted Shift Assignments for the booking, matching the assigned
	Employee's designation to each Event Staff Requirement row.  Safe no-op when
	the Shift Assignment carries no ``event_booking`` link (field absent → None).
	"""
	booking = getattr(doc, "event_booking", None)
	if not booking:
		return
	frappe.db.sql(
		"""
		UPDATE `tabEvent Staff Requirement` esr
		SET esr.qty_assigned = (
			SELECT COUNT(*)
			FROM `tabShift Assignment` sa
			INNER JOIN `tabEmployee` emp ON emp.name = sa.employee
			WHERE sa.event_booking = %(booking)s
			  AND sa.docstatus = 1
			  AND emp.designation = esr.designation
		)
		WHERE esr.parent = %(booking)s
		  AND esr.parenttype = 'Event Booking'
		""",
		{"booking": booking},
	)
