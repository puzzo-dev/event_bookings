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
		"status": "New",
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
		self.assertEqual(doc.status, "New")

		doc.status = "Quoted"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.status, "Quoted")

	def test_any_manual_status_transition_allowed(self):
		"""Manual jumps (New → Paid) stay allowed — humans move freely;
		only automation is forward-only (see tests/test_status_automation.py)."""
		doc = _make_booking("Test Any Transition")
		doc.insert(ignore_permissions=True)

		doc.status = "Paid"
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.status, "Paid")

	def test_booking_is_submittable(self):
		"""Event Booking is submittable at any status — the status
		is driven by linked documents (Quotation/SO/SI), not by the submit
		action. Same as Sales Order in ERPNext."""
		doc = _make_booking("Test Submit at New", status="New")
		doc.insert(ignore_permissions=True)
		doc.submit()
		self.assertEqual(doc.docstatus, 1)

		doc = _make_booking("Test Submit at Confirmed", status="Confirmed")
		doc.insert(ignore_permissions=True)
		doc.submit()
		self.assertEqual(doc.docstatus, 1)

	def test_search_fields_hold_no_date_field(self):
		"""No Date/Datetime/Time field may appear in search_fields.

		Event Booking is registered as an Accounting Dimension, so every link
		field to it is searched through erpnext.controllers.queries.
		get_filtered_dimensions. That function LIKEs every entry of
		get_search_fields() without checking the fieldtype:

		    for field in searchfields:
		        or_filters.append([field, "LIKE", "%%%s%%" % txt])

		DatabaseQuery.prepare_filter_condition then routes a Date field to
		frappe.db.format_date(), which cannot parse "%txt%" and throws
		"<value> is not a valid date string" — a 417 on every keystroke in the
		link field. Frappe's own search path whitelists the fieldtypes it will
		LIKE and so never hits this; the dimension query does not.
		"""
		meta = frappe.get_meta("Event Booking")
		offenders = []
		for fieldname in meta.get_search_fields():
			df = meta.get_field(fieldname)
			if df and df.fieldtype in ("Date", "Datetime", "Time"):
				offenders.append(f"{fieldname} ({df.fieldtype})")

		self.assertEqual(
			offenders,
			[],
			"search_fields must not contain a date-like field; "
			f"found {offenders}. See get_filtered_dimensions.",
		)

	def test_link_field_shows_the_event_name(self):
		"""A link to a booking must identify the event, not just show an ID."""
		meta = frappe.get_meta("Event Booking")
		self.assertEqual(meta.title_field, "event_name")
		self.assertTrue(meta.show_title_field_in_link)
