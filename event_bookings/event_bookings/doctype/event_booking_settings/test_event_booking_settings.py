# Copyright (c) 2026, Avril Beetails and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestEventBookingSettings(FrappeTestCase):
	def test_settings_exists(self):
		self.assertTrue(frappe.db.exists("Event Booking Settings", "Event Booking Settings"))

	def test_auto_create_requires_default_cost_center(self):
		from event_bookings.event_bookings.doctype.event_booking_settings.event_booking_settings import EventBookingSettings
		doc = frappe.new_doc("Event Booking Settings")
		doc.auto_create_cost_center_per_event = 1
		doc.default_cost_center = None
		self.assertRaises(frappe.ValidationError, doc.validate)
