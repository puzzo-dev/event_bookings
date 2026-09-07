"""Quotation-first flow tests: Event Booking created FROM a submitted Quotation.

Covers:
- make_event_booking mapper (customer resolution, prefilled status, quotation link)
- after_insert reverse-link write-back
- Event Booking can only be created from a submitted Quotation
- One Event Booking per Quotation (duplicate prevention)
- Sales Order created from a Quotation auto-links to the Event Booking
"""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from event_bookings.event_bookings.doctype.event_booking.event_booking import (
	make_event_booking,
)
from event_bookings.tests.fixtures import (
	ensure_test_customer_leaf_details,
	get_or_create_test_customer,
	get_or_create_test_event_type,
	get_or_create_test_item,
)

ERPNEXT_INSTALLED = "erpnext" in frappe.get_installed_apps()


def _make_quotation(party_name, submit=True):
	item = get_or_create_test_item("Test Event Service Item")
	qt = frappe.get_doc(
		{
			"doctype": "Quotation",
			"quotation_to": "Customer",
			"party_name": party_name,
			"company": frappe.db.get_value("Company", {}, "name", order_by="creation asc"),
			"transaction_date": frappe.utils.today(),
			"items": [{"item_code": item, "qty": 1, "rate": 100}],
		}
	).insert(ignore_permissions=True)
	if submit:
		qt.submit()
	return qt


@unittest.skipUnless(ERPNEXT_INSTALLED, "quotation-first flow requires ERPNext")
class TestQuotationToBooking(FrappeTestCase):
	def setUp(self):
		ensure_test_customer_leaf_details()
		self.test_customer = get_or_create_test_customer()
		self.test_event_type = get_or_create_test_event_type()

	def tearDown(self):
		frappe.db.rollback()

	def _fill_and_insert_booking(self, booking, event_name="Mapped Wedding"):
		booking.event_name = event_name
		booking.event_type = self.test_event_type
		booking.event_date = frappe.utils.add_days(frappe.utils.today(), 30)
		booking.event_time = "18:00:00"
		booking.event_location = "Grand Ballroom"
		booking.insert(ignore_permissions=True)
		return booking

	def test_make_event_booking_from_submitted_quotation(self):
		qt = _make_quotation(self.test_customer)

		booking = make_event_booking(qt.name)
		self.assertEqual(booking.doctype, "Event Booking")
		self.assertEqual(booking.customer, qt.party_name)
		self.assertEqual(booking.quotation, qt.name)
		self.assertEqual(booking.booking_status, "Quoted")
		self.assertEqual(booking.company, qt.company)

		booking = self._fill_and_insert_booking(booking)

		# after_insert writes the reverse link (one booking per quotation)
		self.assertEqual(
			frappe.db.get_value("Quotation", qt.name, "event_booking"), booking.name
		)

	def test_make_event_booking_rejects_draft_quotation(self):
		from frappe.exceptions import ValidationError

		qt = _make_quotation(self.test_customer, submit=False)
		with self.assertRaises(ValidationError):
			make_event_booking(qt.name)

	def test_make_event_booking_rejects_duplicate(self):
		from frappe.exceptions import ValidationError

		qt = _make_quotation(self.test_customer)
		booking1 = self._fill_and_insert_booking(make_event_booking(qt.name))

		# A second booking from the same quotation should be rejected
		with self.assertRaises(ValidationError):
			self._fill_and_insert_booking(
				make_event_booking(qt.name), event_name="Duplicate"
			)

	def test_make_event_booking_rejects_unreadable_quotation(self):
		from frappe.exceptions import PermissionError

		qt = _make_quotation(self.test_customer)
		# Simulate a caller without read permission on the quotation
		frappe.set_user("Guest")
		try:
			with self.assertRaises(PermissionError):
				make_event_booking(qt.name)
		finally:
			frappe.set_user("Administrator")

	def test_make_event_booking_rejects_invalid_party_type(self):
		from frappe.exceptions import ValidationError

		qt = _make_quotation(self.test_customer)
		frappe.db.set_value("Quotation", qt.name, "quotation_to", "Prospect")
		with self.assertRaises(ValidationError):
			make_event_booking(qt.name)


@unittest.skipUnless(ERPNEXT_INSTALLED, "SO auto-link requires ERPNext")
class TestSalesOrderAutoLink(FrappeTestCase):
	"""When a Sales Order is created from a Quotation that's linked to an
	Event Booking, the SO should automatically get the event_booking link —
	regardless of whether it was created from the EB form or directly from
	the Quotation.
	"""

	def setUp(self):
		ensure_test_customer_leaf_details()
		self.test_customer = get_or_create_test_customer()
		self.test_event_type = get_or_create_test_event_type()

	def tearDown(self):
		frappe.db.rollback()

	def test_so_inherits_event_booking_from_quotation(self):
		from erpnext.selling.doctype.quotation.quotation import make_sales_order

		qt = _make_quotation(self.test_customer)
		booking = make_event_booking(qt.name)
		booking.event_name = "Auto-Link Test"
		booking.event_type = self.test_event_type
		booking.event_date = frappe.utils.add_days(frappe.utils.today(), 30)
		booking.event_time = "18:00:00"
		booking.event_location = "Hall"
		booking.insert(ignore_permissions=True)

		# Create SO directly from the Quotation (not from the EB form)
		so = make_sales_order(qt.name)
		so.delivery_date = frappe.utils.add_days(frappe.utils.today(), 7)
		so.insert(ignore_permissions=True)

		# The SO should have inherited the event_booking link
		self.assertEqual(so.event_booking, booking.name)
		# And the EB should have the sales_order link
		self.assertEqual(
			frappe.db.get_value("Event Booking", booking.name, "sales_order"), so.name
		)


@unittest.skipUnless(ERPNEXT_INSTALLED, "Stock Entry creation requires ERPNext")
class TestStockEntryCreation(FrappeTestCase):
	"""Create Stock Entry from Event Booking — prefill + link verification."""

	def setUp(self):
		ensure_test_customer_leaf_details()
		self.test_customer = get_or_create_test_customer()
		self.test_event_type = get_or_create_test_event_type()

	def tearDown(self):
		frappe.db.rollback()

	def _make_booking(self):
		qt = _make_quotation(self.test_customer)
		booking = make_event_booking(qt.name)
		booking.event_name = "Stock Entry Test"
		booking.event_type = self.test_event_type
		booking.event_date = frappe.utils.add_days(frappe.utils.today(), 30)
		booking.event_time = "18:00:00"
		booking.event_location = "Hall"
		booking.company = frappe.defaults.get_user_default("Company")
		booking.insert(ignore_permissions=True)
		return booking

	def test_make_stock_entry_links_event_booking(self):
		from event_bookings.event_bookings.doctype.event_booking.event_booking import make_stock_entry

		booking = self._make_booking()
		se_dict = make_stock_entry(booking.name, "Material Issue")
		self.assertEqual(se_dict["event_booking"], booking.name)
		self.assertEqual(se_dict["stock_entry_type"], "Material Issue")
		self.assertEqual(se_dict["company"], booking.company)

	def test_make_stock_entry_permission_denied(self):
		from event_bookings.event_bookings.doctype.event_booking.event_booking import make_stock_entry
		from frappe.exceptions import PermissionError

		booking = self._make_booking()
		frappe.set_user("Guest")
		try:
			with self.assertRaises(PermissionError):
				make_stock_entry(booking.name, "Material Issue")
		finally:
			frappe.set_user("Administrator")


@unittest.skipUnless(ERPNEXT_INSTALLED, "Connections requires ERPNext")
class TestEventBookingConnections(FrappeTestCase):
	"""Verify the Event Booking DocType has connections configured."""

	def test_links_include_stock_entry(self):
		"""The DocType JSON should include Stock Entry in its links."""
		meta = frappe.get_meta("Event Booking")
		link_doctypes = [l.link_doctype for l in meta.links]
		self.assertIn("Stock Entry", link_doctypes)
		self.assertIn("Quotation", link_doctypes)
		self.assertIn("Sales Order", link_doctypes)
		self.assertIn("Sales Invoice", link_doctypes)
