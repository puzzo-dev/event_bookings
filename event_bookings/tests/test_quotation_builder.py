import frappe
from frappe.tests.utils import FrappeTestCase

from event_bookings.tests.fixtures import (
	get_or_create_test_party,
	get_or_create_test_event_type,
	get_or_create_test_item,
)


class TestQuotationBuilder(FrappeTestCase):
	def setUp(self):
		if "erpnext" not in frappe.get_installed_apps():
			self.skipTest("Quotation tests require ERPNext")
		self.test_party_type, self.test_party_name = get_or_create_test_party()
		self.test_event_type = get_or_create_test_event_type()

	def tearDown(self):
		frappe.db.rollback()

	def test_quotation_creation(self):
		doc = frappe.get_doc(
			{
				"doctype": "Event Booking",
				"event_name": "Test Quotation Event",
				"party_type": self.test_party_type,
				"party_name": self.test_party_name,
				"event_type": self.test_event_type,
				"event_date": frappe.utils.add_days(frappe.utils.today(), 7),
				"event_time": "18:00:00",
				"event_location": "Test Venue",
				"booking_status": "New",
				"booking_date": frappe.utils.now(),
			}
		)
		doc.insert(ignore_permissions=True)

		# Manually create quotation via action button equivalent
		doc.create_quotation()
		doc.save(ignore_permissions=True)

		self.assertTrue(doc.quotation)
		qt = frappe.get_doc("Quotation", doc.quotation)
		self.assertEqual(qt.party_name, self.test_party_name)
		self.assertEqual(len(qt.items), 0)
