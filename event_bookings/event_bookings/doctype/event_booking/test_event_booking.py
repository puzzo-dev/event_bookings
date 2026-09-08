# Copyright (c) 2026, I-Varse Technologies NG and Contributors
# See license.txt

import unittest

import frappe
from event_bookings.tests.compat import FrappeTestCase

from event_bookings.tests.fixtures import (
	get_or_create_test_customer,
	get_or_create_test_event_type,
)

ERPNEXT_INSTALLED = "erpnext" in frappe.get_installed_apps()


def _make_booking(event_name, **kwargs):
	"""Build a minimal insertable Event Booking using shared fixtures."""
	defaults = {
		"doctype": "Event Booking",
		"event_name": event_name,
		"customer": get_or_create_test_customer(),
		"booking_status": "New",
		"booking_date": frappe.utils.today(),
		"event_time": "10:00:00",
		"event_location": "Test Venue",
		"event_date": frappe.utils.add_days(frappe.utils.today(), 30),
		"event_type": get_or_create_test_event_type(),
	}
	defaults.update(kwargs)
	return frappe.get_doc(defaults)


@unittest.skipUnless(ERPNEXT_INSTALLED, "bookings require a Customer (quotation-first flow)")
class TestEventBooking(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_event_booking_creation(self):
		doc = _make_booking("Test Event")
		doc.insert(ignore_permissions=True)
		self.assertTrue(doc.name)
		self.assertTrue(doc.name.startswith("EVT-"))

	def test_valid_status_transition(self):
		"""Manual forward transition (New → Quoted) is accepted on save."""
		doc = _make_booking("Test Transition")
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.booking_status, "New")

		doc.booking_status = "Quoted"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.booking_status, "Quoted")

	def test_any_manual_status_transition_allowed(self):
		"""Manual jumps (New → Paid) stay allowed — humans move freely;
		only automation is forward-only (see tests/test_status_automation.py)."""
		doc = _make_booking("Test Any Transition")
		doc.insert(ignore_permissions=True)

		doc.booking_status = "Paid"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.booking_status, "Paid")

	def test_booking_is_submittable(self):
		"""Event Booking is submittable at any booking_status — the status
		is driven by linked documents (Quotation/SO/SI), not by the submit
		action. Same as Sales Order in ERPNext."""
		doc = _make_booking("Test Submit at New", booking_status="New")
		doc.insert(ignore_permissions=True)
		doc.submit()
		self.assertEqual(doc.docstatus, 1)

		doc = _make_booking("Test Submit at Confirmed", booking_status="Confirmed")
		doc.insert(ignore_permissions=True)
		doc.submit()
		self.assertEqual(doc.docstatus, 1)
