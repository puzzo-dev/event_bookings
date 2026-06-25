"""Utility helpers for outbound WhatsApp notifications sent from event_bookings."""

from __future__ import annotations

import re

import frappe


def format_whatsapp_message(template: str, doc) -> str:
	"""Render a WhatsApp message template using fields from a Frappe document.

	Placeholder syntax: {field_name}.  event_date values are formatted through
	frappe.utils.formatdate so the recipient sees a locale-aware date string.

	Raises frappe.ValidationError (via frappe.throw) if the template references
	a field that does not exist on the document.
	"""
	placeholders = re.findall(r"\{(\w+)\}", template)
	values: dict[str, str] = {}
	for key in placeholders:
		if not hasattr(doc, key):
			frappe.log_error(
				title=f"WhatsApp template missing field '{key}'",
				message=f"Document type: {getattr(doc, 'doctype', 'unknown')}",
			)
			frappe.throw(
				f"Template placeholder '{{{key}}}' is not a valid field on this document."
			)
		raw = getattr(doc, key) or ""
		if key == "event_date" and raw:
			raw = frappe.utils.formatdate(raw)
		values[key] = str(raw)

	return template.format(**values)
