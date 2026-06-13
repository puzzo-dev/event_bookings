import frappe


def on_quotation_submit(doc, method):
    if doc.event_booking:
        eb = frappe.get_doc("Event Booking", doc.event_booking)
        eb.quotation = doc.name
        eb.save(ignore_permissions=True)


def on_sales_order_submit(doc, method):
    if doc.event_booking:
        eb = frappe.get_doc("Event Booking", doc.event_booking)
        eb.sales_order = doc.name
        eb.total_actual = doc.grand_total
        eb.save(ignore_permissions=True)


def on_sales_invoice_submit(doc, method):
    if doc.event_booking:
        eb = frappe.get_doc("Event Booking", doc.event_booking)
        eb.sales_invoice = doc.name
        eb.save(ignore_permissions=True)


def on_stock_entry_submit(doc, method):
    if doc.event_booking and doc.stock_entry_type == "Material Issue":
        eb = frappe.get_doc("Event Booking", doc.event_booking)
        eb.save(ignore_permissions=True)


def on_shift_assignment_update(doc, method):
    if doc.event_booking:
        eb = frappe.get_doc("Event Booking", doc.event_booking)
        eb.update_staff_assignment_counts()
        eb.save(ignore_permissions=True)
