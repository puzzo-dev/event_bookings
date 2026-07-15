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

	def test_valid_status_transition(self):
		"""Valid transitions (New → Quoted) should be accepted on save."""
		doc = frappe.new_doc("Event Booking")
		doc.event_name = "Test Transition"
		doc.booking_status = "New"
		doc.party_type = "Individual"
		doc.party_name = "Test Party"
		doc.event_type = "Wedding"
		doc.event_date = frappe.utils.add_days(frappe.utils.today(), 30)
		doc.event_time = "10:00:00"
		doc.event_location = "Test Venue"
		doc.insert()
		self.assertEqual(doc.booking_status, "New")

		doc.booking_status = "Quoted"
		doc.save()
		self.assertEqual(doc.booking_status, "Quoted")

	def test_invalid_status_transition(self):
		"""Invalid transitions (New → Paid) should be rejected."""
		doc = frappe.new_doc("Event Booking")
		doc.event_name = "Test Invalid Transition"
		doc.booking_status = "New"
		doc.party_type = "Individual"
		doc.party_name = "Test Party"
		doc.event_type = "Wedding"
		doc.event_date = frappe.utils.add_days(frappe.utils.today(), 30)
		doc.event_time = "10:00:00"
		doc.event_location = "Test Venue"
		doc.insert()

		doc.booking_status = "Paid"
		with self.assertRaises(frappe.ValidationError):
			doc.save()
