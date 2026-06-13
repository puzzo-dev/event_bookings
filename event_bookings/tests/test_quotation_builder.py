import frappe
from frappe.tests.utils import FrappeTestCase

from event_bookings.tests.fixtures import (
	get_or_create_test_customer,
	get_or_create_test_event_type,
	get_or_create_test_item,
)


class TestQuotationBuilder(FrappeTestCase):
	def setUp(self):
		self.test_customer = get_or_create_test_customer()
		self.test_event_type = get_or_create_test_event_type()

	def tearDown(self):
		frappe.db.rollback()

	def test_quotation_creation(self):
		item_code = get_or_create_test_item("TEST-SVC-001")
		doc = frappe.get_doc(
			{
				"doctype": "Event Booking",
				"event_name": "Test Quotation Event",
				"customer": self.test_customer,
				"event_type": self.test_event_type,
				"event_date": frappe.utils.add_days(frappe.utils.today(), 7),
				"event_time": "18:00:00",
				"event_location": "Test Venue",
				"booking_status": "New",
				"services": [
					{
						"item": item_code,
						"item_name": item_code,
						"qty": 10,
						"rate": 500,
						"amount": 5000,
					}
				],
			}
		)
		doc.insert(ignore_permissions=True)

		# Trigger Quoted status to create quotation
		doc.booking_status = "Quoted"
		doc.save(ignore_permissions=True)

		self.assertTrue(doc.quotation)
		qt = frappe.get_doc("Quotation", doc.quotation)
		self.assertEqual(qt.party_name, self.test_customer)
		self.assertEqual(len(qt.items), 1)
