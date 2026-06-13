import frappe
from frappe.tests.utils import FrappeTestCase


class TestEventBooking(FrappeTestCase):
    def setUp(self):
        self.test_customer = self._create_test_customer()
        self.test_event_type = self._create_test_event_type()

    def tearDown(self):
        frappe.db.rollback()

    def _create_test_customer(self):
        if not frappe.db.exists("Customer", "Test Event Customer"):
            doc = frappe.get_doc(
                {
                    "doctype": "Customer",
                    "customer_name": "Test Event Customer",
                    "customer_type": "Individual",
                }
            )
            doc.insert(ignore_permissions=True)
        return "Test Event Customer"

    def _create_test_event_type(self):
        if not frappe.db.exists("Event Type", "Test Event"):
            doc = frappe.get_doc({"doctype": "Event Type", "type_name": "Test Event"})
            doc.insert(ignore_permissions=True)
        return "Test Event"

    def test_event_booking_creation(self):
        doc = frappe.get_doc(
            {
                "doctype": "Event Booking",
                "event_name": "Test Birthday Party",
                "customer": self.test_customer,
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

    def test_total_estimated_calculation(self):
        doc = frappe.get_doc(
            {
                "doctype": "Event Booking",
                "event_name": "Test Calculation",
                "customer": self.test_customer,
                "event_type": self.test_event_type,
                "event_date": frappe.utils.add_days(frappe.utils.today(), 7),
                "event_time": "18:00:00",
                "event_location": "Test Venue",
                "booking_status": "New",
                "services": [
                    {
                        "item": "Test Item",
                        "item_name": "Test Item",
                        "qty": 10,
                        "rate": 500,
                        "amount": 5000,
                    }
                ],
            }
        )
        doc.insert(ignore_permissions=True)
        self.assertEqual(doc.total_estimated, 5000)

    def test_past_date_validation(self):
        from frappe.exceptions import ValidationError

        doc = frappe.get_doc(
            {
                "doctype": "Event Booking",
                "event_name": "Test Past Date",
                "customer": self.test_customer,
                "event_type": self.test_event_type,
                "event_date": frappe.utils.add_days(frappe.utils.today(), -1),
                "event_time": "18:00:00",
                "event_location": "Test Venue",
                "booking_status": "New",
            }
        )
        with self.assertRaises(ValidationError):
            doc.insert(ignore_permissions=True)
