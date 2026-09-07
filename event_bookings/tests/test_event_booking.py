import frappe
from frappe.tests.utils import FrappeTestCase

from event_bookings.tests.fixtures import get_or_create_test_customer, get_or_create_test_event_type


def _make_booking(**kwargs):
	"""Helper: build a minimal Event Booking dict with a Customer link."""
	defaults = {
		"doctype": "Event Booking",
		"customer": get_or_create_test_customer(),
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
			customer=self.test_customer,
			event_type=self.test_event_type,
			event_date=frappe.utils.add_days(frappe.utils.today(), 7),
		)
		doc.insert(ignore_permissions=True)
		self.assertTrue(doc.name)
		self.assertTrue(doc.name.startswith("EVT-"))

	def test_total_estimated_zero_without_linked_quotation(self):
		doc = _make_booking(
			event_name="Test Calculation",
			customer=self.test_customer,
			event_type=self.test_event_type,
			event_date=frappe.utils.add_days(frappe.utils.today(), 7),
		)
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.total_estimated, 0)

	def test_past_date_validation(self):
		"""Past-date guard semantics (P1-7):
		- back-dating a NEW booking is allowed (recording events that ran)
		- MOVING an existing booking's date into the past is blocked
		- re-saving a legacy past-dated booking without touching the date
		  must not be blocked (submit/cancel run the full validate chain)
		"""
		from frappe.exceptions import ValidationError

		past = frappe.utils.add_days(frappe.utils.today(), -7)
		future = frappe.utils.add_days(frappe.utils.today(), 7)

		# 1. New booking with a past date — back-entry allowed
		doc = _make_booking(
			event_name="Test Backdated Event",
			customer=self.test_customer,
			event_type=self.test_event_type,
			event_date=past,
		)
		doc.insert(ignore_permissions=True)
		self.assertTrue(doc.name)

		# 2. Legacy past-dated booking saves freely while the date is unchanged
		doc.guest_count = 120
		doc.save(ignore_permissions=True)
		self.assertEqual(doc.guest_count, 120)

		# 3. Moving an existing booking's date into the past is blocked
		doc2 = _make_booking(
			event_name="Test Move To Past",
			customer=self.test_customer,
			event_type=self.test_event_type,
			event_date=future,
		)
		doc2.insert(ignore_permissions=True)
		doc2.event_date = past
		with self.assertRaises(ValidationError):
			doc2.save(ignore_permissions=True)
