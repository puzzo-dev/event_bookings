# Notifications helper
# Frappe's built-in Notification DocType handles email triggers.
# This module is a placeholder for WhatsApp / custom channel formatting.


def format_whatsapp_message(template, doc):
    """Format a WhatsApp message from a template string and document."""
    from frappe.utils import formatdate

    return template.format(
        event_name=doc.event_name,
        customer=doc.customer,
        event_date=formatdate(doc.event_date),
        event_location=doc.event_location,
    )
