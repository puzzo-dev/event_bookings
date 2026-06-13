# Copyright (c) 2026, Avril Beetails and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import validate_email_address


class EventSettings(Document):
	def validate(self):
		self.validate_notification_email()

	def validate_notification_email(self):
		if self.notification_email:
			validate_email_address(self.notification_email, throw=True)
