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
            "customer": self.customer,
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
        eb = self._make_event(event_cost_center=parent_cc)
        self.assertEqual(eb.event_cost_center, parent_cc)

    def test_cost_center_can_be_created_from_form(self):
        """User can create a new Cost Center from the Event Booking form Link field."""
        parent_cc = frappe.db.get_value(
            "Cost Center", {"company": frappe.defaults.get_defaults().get("company"), "is_group": 1}, "name"
        )
        cc = frappe.get_doc({
            "doctype": "Cost Center",
            "cost_center_name": "_Test Event CC",
            "parent_cost_center": parent_cc,
            "company": frappe.defaults.get_defaults().get("company"),
            "is_event_cost_center": 1,
        }).insert(ignore_permissions=True)

        eb = self._make_event(event_cost_center=cc.name)
        self.assertEqual(eb.event_cost_center, cc.name)
        self.assertEqual(cc.is_event_cost_center, 1)
        self.assertEqual(cc.parent_cost_center, parent_cc)

    def test_naming_series_format(self):
        eb = self._make_event()
        self.assertTrue(eb.name.startswith("EVT-"), f"Name {eb.name} should start with EVT-")
