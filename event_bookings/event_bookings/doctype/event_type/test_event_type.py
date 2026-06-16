# Copyright (c) 2026, Avril Beetails and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestEventType(FrappeTestCase):
	def test_event_type_creation(self):
		doc = frappe.new_doc("Event Type")
		doc.type_name = "Test Type"
		self.assertTrue(doc.type_name)

	def test_event_type_permissions(self):
		perms = frappe.get_meta("Event Type").permissions
		roles = {p.role for p in perms}
		self.assertIn("Event Manager", roles)
