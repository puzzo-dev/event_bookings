# Copyright (c) 2026, Avril Beetails and Contributors
# See license.txt

import frappe
from event_bookings.tests.compat import FrappeTestCase


class TestEventBookingSettings(FrappeTestCase):
	def test_settings_exists(self):
		self.assertTrue(frappe.db.exists("Event Booking Settings", "Event Booking Settings"))

