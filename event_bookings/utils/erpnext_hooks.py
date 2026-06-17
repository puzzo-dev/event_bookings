import frappe


def _update_linked_event_booking(doc, callback=None, **field_updates):
	"""Fetch the linked Event Booking and apply field updates.

	If the Event Booking cannot be successfully updated, the error will bubble up
	and roll back the ERPNext document submission to ensure data consistency.
	"""
	if not getattr(doc, "event_booking", None):
		return

	eb = frappe.get_doc("Event Booking", doc.event_booking)
	for field, value in field_updates.items():
		setattr(eb, field, value)
	if callback:
		callback(eb)

	# Event Booking is not submittable (docstatus always 0); always use save()
	# so that validate, before_save, and version tracking fire correctly.
	try:
		eb.save()
	except frappe.ValidationError:
		frappe.log_error(title=f"Failed to update linked Event Booking {eb.name} on submit of {doc.doctype} {doc.name}")
		# We do not re-raise because we don't want to block the ERPNext document submission


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
