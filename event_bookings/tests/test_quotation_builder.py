import frappe
from frappe.tests.utils import FrappeTestCase


class TestQuotationBuilder(FrappeTestCase):
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

    def _create_test_item(self, item_code):
        if not frappe.db.exists("Item", item_code):
            doc = frappe.get_doc(
                {
                    "doctype": "Item",
                    "item_code": item_code,
                    "item_name": item_code,
                    "item_group": "Services",
                    "stock_uom": "Nos",
                    "is_stock_item": 0,
                    "standard_rate": 500,
                }
            )
            doc.insert(ignore_permissions=True)
        return item_code

    def test_quotation_creation(self):
        item_code = self._create_test_item("TEST-SVC-001")
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
