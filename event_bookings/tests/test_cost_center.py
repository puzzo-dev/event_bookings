import frappe
from frappe.tests.utils import FrappeTestCase


class TestEventCostCenter(FrappeTestCase):
    def setUp(self):
        cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
        if not frappe.db.exists("Customer", "_Test CC Customer"):
            frappe.get_doc(
                {
                    "doctype": "Customer",
                    "customer_name": "_Test CC Customer",
                    "customer_type": "Individual",
                    "customer_group": cg,
                }
            ).insert(ignore_permissions=True)
        if not frappe.db.exists("Event Type", "_Test"):
            frappe.get_doc({"doctype": "Event Type", "type_name": "_Test"}).insert(
                ignore_permissions=True
            )
        self.customer = "_Test CC Customer"
        self.event_type = "_Test"

    def tearDown(self):
        frappe.db.rollback()

    def _make_event(self, **kwargs):
        defaults = {
            "doctype": "Event Booking",
            "event_name": "Cost Center Test Event",
            "party_type": "Customer",
            "party_name": self.customer,
            "event_type": self.event_type,
            "event_date": frappe.utils.add_days(frappe.utils.today(), 14),
            "event_time": "18:00:00",
            "event_location": "Test Venue",
            "booking_status": "New",
            "booking_date": frappe.utils.today(),
        }
        defaults.update(kwargs)
        doc = frappe.get_doc(defaults)
        doc.insert(ignore_permissions=True)
        return doc

    def test_manual_cost_center_selection(self):
        """User can manually select a Cost Center on the Event Booking form."""
        parent_cc = frappe.db.get_value(
            "Cost Center", {"company": frappe.defaults.get_defaults().get("company"), "is_group": 0}, "name"
        )
        eb = self._make_event(cost_center=parent_cc)
        self.assertEqual(eb.cost_center, parent_cc)

    def test_naming_series_format(self):
        eb = self._make_event()
        self.assertTrue(eb.name.startswith("EVT-"), f"Name {eb.name} should start with EVT-")
