# Notifications helper
# Frappe's built-in Notification DocType handles email triggers.
# This module is a placeholder for WhatsApp / custom channel formatting.

import re

from frappe.utils import cstr

ALLOWED_PLACEHOLDERS = {"event_name", "customer", "event_date", "event_location"}
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def format_whatsapp_message(template, doc):
    """Format a WhatsApp message from a template string and document.

    Uses explicit placeholder substitution to prevent format-string injection.
    Only the whitelisted placeholders are resolved; unknown placeholders are
    left as-is.
    """
    from frappe.utils import formatdate

    values = {
        "event_name": cstr(doc.event_name),
        "customer": cstr(doc.customer),
        "event_date": formatdate(doc.event_date),
        "event_location": cstr(doc.event_location),
    }

    def _replace(match):
        key = match.group(1)
        if key in ALLOWED_PLACEHOLDERS:
            return values[key]
        return match.group(0)

    return _PLACEHOLDER_RE.sub(_replace, template)
