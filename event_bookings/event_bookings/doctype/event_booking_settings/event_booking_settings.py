# Copyright (c) 2026, Avril Beetails and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class EventBookingSettings(Document):
	def validate(self):
		if self.auto_create_cost_center_per_event and not self.default_cost_center:
			frappe.throw(_("Default Cost Center is required when Auto-Create Cost Center Per Event is enabled."))
