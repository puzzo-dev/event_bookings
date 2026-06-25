import frappe
from frappe.tests.utils import FrappeTestCase

from event_bookings.tests.fixtures import get_or_create_test_customer, get_or_create_test_event_type


def _make_booking(**kwargs):
	"""Helper: build a minimal Event Booking dict using party_type/party_name."""
	defaults = {
		"doctype": "Event Booking",
		"party_type": "Customer",
		"booking_status": "New",
		"booking_date": frappe.utils.today(),
		"event_time": "18:00:00",
		"event_location": "Test Venue",
	}
	defaults.update(kwargs)
	return frappe.get_doc(defaults)


class TestEventBooking(FrappeTestCase):
	def setUp(self):
		self.test_customer = get_or_create_test_customer()
		self.test_event_type = get_or_create_test_event_type()

	def tearDown(self):
		frappe.db.rollback()

	def test_event_booking_creation(self):
		doc = _make_booking(
			event_name="Test Birthday Party",
			party_name=self.test_customer,
			event_type=self.test_event_type,
			event_date=frappe.utils.add_days(frappe.utils.today(), 7),
		)
		doc.insert(ignore_permissions=True)
		self.assertTrue(doc.name)
		self.assertTrue(doc.name.startswith("EVT-"))

	def test_total_estimated_zero_without_linked_quotation(self):
		doc = _make_booking(
			event_name="Test Calculation",
			party_name=self.test_customer,
			event_type=self.test_event_type,
			event_date=frappe.utils.add_days(frappe.utils.today(), 7),
		)
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.total_estimated, 0)

	def test_past_date_validation(self):
		from frappe.exceptions import ValidationError

		doc = _make_booking(
			event_name="Test Past Date",
			party_name=self.test_customer,
			event_type=self.test_event_type,
			event_date=frappe.utils.add_days(frappe.utils.today(), -1),
		)
		with self.assertRaises(ValidationError):
			doc.insert(ignore_permissions=True)
