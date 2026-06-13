import frappe


def on_quotation_submit(doc, method):
	if not doc.event_booking:
		return
	try:
		eb = frappe.get_doc("Event Booking", doc.event_booking)
		eb.quotation = doc.name
		eb.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(title=f"Event Booking link failed on Quotation {doc.name}")
		frappe.msgprint(
			f"Could not update Event Booking {doc.event_booking}. Check the Error Log.",
			indicator="orange",
			alert=True,
		)


def on_sales_order_submit(doc, method):
	if not doc.event_booking:
		return
	try:
		eb = frappe.get_doc("Event Booking", doc.event_booking)
		eb.sales_order = doc.name
		eb.total_actual = doc.grand_total
		eb.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(title=f"Event Booking link failed on Sales Order {doc.name}")
		frappe.msgprint(
			f"Could not update Event Booking {doc.event_booking}. Check the Error Log.",
			indicator="orange",
			alert=True,
		)


def on_sales_invoice_submit(doc, method):
	if not doc.event_booking:
		return
	try:
		eb = frappe.get_doc("Event Booking", doc.event_booking)
		eb.sales_invoice = doc.name
		eb.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(title=f"Event Booking link failed on Sales Invoice {doc.name}")
		frappe.msgprint(
			f"Could not update Event Booking {doc.event_booking}. Check the Error Log.",
			indicator="orange",
			alert=True,
		)


def on_stock_entry_submit(doc, method):
	if not (doc.event_booking and doc.stock_entry_type == "Material Issue"):
		return
	try:
		eb = frappe.get_doc("Event Booking", doc.event_booking)
		eb.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(title=f"Event Booking link failed on Stock Entry {doc.name}")
		frappe.msgprint(
			f"Could not update Event Booking {doc.event_booking}. Check the Error Log.",
			indicator="orange",
			alert=True,
		)


def on_shift_assignment_update(doc, method):
	if not doc.event_booking:
		return
	try:
		eb = frappe.get_doc("Event Booking", doc.event_booking)
		eb.update_staff_assignment_counts()
		eb.save(ignore_permissions=True)
	except Exception:
		frappe.log_error(title=f"Event Booking staff update failed on Shift Assignment {doc.name}")
		frappe.msgprint(
			f"Could not update Event Booking {doc.event_booking}. Check the Error Log.",
			indicator="orange",
			alert=True,
		)
