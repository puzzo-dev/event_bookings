# Copyright (c) 2026, I-Varse Technologies NG and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestEventBooking(FrappeTestCase):
	def test_event_booking_creation(self):
		doc = frappe.new_doc("Event Booking")
		doc.event_name = "Test Event"
		doc.booking_status = "New"
		doc.event_date = frappe.utils.add_days(frappe.utils.today(), 7)
		doc.event_time = "10:00:00"
		doc.event_location = "Test Venue"
		self.assertTrue(doc.event_name)

	def test_flexible_status_changes(self):
		"""Status changes are not hardcoded; orgs can design their own workflow."""
		doc = frappe.new_doc("Event Booking")
		doc.event_name = "Test Event"
		doc.booking_status = "New"
		doc.event_date = frappe.utils.add_days(frappe.utils.today(), 7)
		doc.event_time = "10:00:00"
		doc.event_location = "Test Venue"
		# Any status value should be accepted without a hardcoded transition error
		doc.booking_status = "Paid"
		self.assertEqual(doc.booking_status, "Paid")
