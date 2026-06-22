import frappe


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


def on_sales_order_submit(doc, method):
	_update_linked_event_booking(doc, sales_order=doc.name)


def on_sales_invoice_submit(doc, method):
	_update_linked_event_booking(doc, sales_invoice=doc.name)


def on_stock_entry_submit(doc, method):
	if doc.stock_entry_type in ("Material Issue", "Material Transfer"):
		_update_linked_event_booking(doc, stock_entry=doc.name)


def on_stock_entry_cancel(doc, method):
	if doc.stock_entry_type in ("Material Issue", "Material Transfer"):
		_update_linked_event_booking(doc, stock_entry=None)


def on_quotation_cancel(doc, method):
	_update_linked_event_booking(doc, quotation=None)


def on_sales_order_cancel(doc, method):
	_update_linked_event_booking(doc, sales_order=None)


def on_sales_invoice_cancel(doc, method):
	_update_linked_event_booking(doc, sales_invoice=None)


def on_material_request_submit(doc, method):
	_update_linked_event_booking(doc, material_request=doc.name)


def on_material_request_cancel(doc, method):
	_update_linked_event_booking(doc, material_request=None)
