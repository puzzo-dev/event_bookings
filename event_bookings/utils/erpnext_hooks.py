import frappe


def _update_linked_event_booking(doc, callback=None, **field_updates):
	"""Fetch the linked Event Booking, apply field updates, and save.

	Errors are logged and surfaced via msgprint so that failures in Event Booking
	back-linking do not block the ERPNext document from being submitted.
	"""
	if not doc.event_booking:
		return
	try:
		eb = frappe.get_doc("Event Booking", doc.event_booking)
		for field, value in field_updates.items():
			setattr(eb, field, value)
		if callback:
			callback(eb)
		eb.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(title=f"Event Booking link failed on {doc.doctype} {doc.name}")
		frappe.msgprint(
			f"Could not update Event Booking {doc.event_booking}. Check the Error Log.",
			indicator="orange",
			alert=True,
		)


def on_quotation_submit(doc, method):
	_update_linked_event_booking(doc, quotation=doc.name)


def on_sales_order_submit(doc, method):
	_update_linked_event_booking(doc, sales_order=doc.name, total_actual=doc.grand_total)


def on_sales_invoice_submit(doc, method):
	_update_linked_event_booking(doc, sales_invoice=doc.name)


def on_stock_entry_submit(doc, method):
	if doc.stock_entry_type == "Material Issue":
		_update_linked_event_booking(doc)


def on_purchase_order_submit(doc, method):
	_update_linked_event_booking(doc)


def on_purchase_invoice_submit(doc, method):
	_update_linked_event_booking(doc, callback=lambda eb: eb.recalculate_purchase_cost())


def on_shift_assignment_update(doc, method):
	_update_linked_event_booking(doc, callback=lambda eb: eb.update_staff_assignment_counts())
