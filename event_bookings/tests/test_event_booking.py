import frappe
from frappe.tests.utils import FrappeTestCase

from event_bookings.tests.fixtures import get_or_create_test_party, get_or_create_test_event_type


class TestEventBooking(FrappeTestCase):
	def setUp(self):
		self.test_party_type, self.test_party_name = get_or_create_test_party()
		self.test_event_type = get_or_create_test_event_type()

	def tearDown(self):
		frappe.db.rollback()

	def test_event_booking_creation(self):
		doc = frappe.get_doc(
			{
				"doctype": "Event Booking",
				"event_name": "Test Birthday Party",
				"party_type": self.test_party_type,
				"party_name": self.test_party_name,
				"event_type": self.test_event_type,
				"event_date": frappe.utils.add_days(frappe.utils.today(), 7),
				"event_time": "18:00:00",
				"event_location": "Test Venue",
				"booking_status": "New",
			}
		)
		doc.insert(ignore_permissions=True)
		self.assertTrue(doc.name)
		self.assertTrue(doc.name.startswith("EVT-"))

	def test_total_estimated_zero_without_linked_quotation(self):
		doc = frappe.get_doc(
			{
				"doctype": "Event Booking",
				"event_name": "Test Calculation",
				"party_type": self.test_party_type,
				"party_name": self.test_party_name,
				"event_type": self.test_event_type,
				"event_date": frappe.utils.add_days(frappe.utils.today(), 7),
				"event_time": "18:00:00",
				"event_location": "Test Venue",
				"booking_status": "New",
			}
		)
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.total_estimated, 0)

	def test_past_date_validation(self):
		from frappe.exceptions import ValidationError

		doc = frappe.get_doc(
			{
				"doctype": "Event Booking",
				"event_name": "Test Past Date",
				"party_type": self.test_party_type,
				"party_name": self.test_party_name,
				"event_type": self.test_event_type,
				"event_date": frappe.utils.add_days(frappe.utils.today(), -1),
				"event_time": "18:00:00",
				"event_location": "Test Venue",
				"booking_status": "New",
			}
		)
		with self.assertRaises(ValidationError):
			doc.insert(ignore_permissions=True)
