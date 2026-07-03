# Notifications helper
# Frappe's built-in Notification DocType handles email triggers.
# This module is a placeholder for WhatsApp / custom channel formatting.


def format_whatsapp_message(template, doc):
	"""Format a WhatsApp message from a template string and document."""
	from frappe.utils import formatdate

	try:
		return template.format(
			event_name=doc.event_name,
			party_name=doc.party_name,
			event_date=formatdate(doc.event_date) if getattr(doc, "event_date", None) else "",
			event_time=str(doc.event_time) if getattr(doc, "event_time", None) else "",
			event_location=doc.event_location,
		)
	except (KeyError, AttributeError) as exc:
		import frappe

		frappe.log_error(title="WhatsApp message formatting failed")
		frappe.throw(f"WhatsApp template contains an unsupported placeholder: {exc}")
