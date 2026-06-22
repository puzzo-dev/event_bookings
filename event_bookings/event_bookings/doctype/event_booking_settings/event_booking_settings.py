# Copyright (c) 2026, Avril Beetails and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class EventBookingSettings(Document):
	def validate(self):
		if self.enable_whatsapp:
			frappe.msgprint(
				_("WhatsApp integration is currently a placeholder and not yet fully implemented."),
				title=_("Feature Pending"),
				indicator="orange"
			)
