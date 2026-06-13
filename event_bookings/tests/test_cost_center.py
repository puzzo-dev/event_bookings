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
        }
        defaults.update(kwargs)
        doc = frappe.get_doc(defaults)
        doc.insert(ignore_permissions=True)
        return doc

    def test_auto_cost_center_disabled_uses_default(self):
        settings = frappe.get_single("Event Settings")
        settings.auto_create_cost_center_per_event = 0
        parent_cc = frappe.db.get_value(
            "Cost Center", {"company": frappe.defaults.get_defaults().get("company"), "is_group": 0}, "name"
        )
        settings.default_cost_center = parent_cc
        settings.save(ignore_permissions=True)

        eb = self._make_event()
        self.assertEqual(eb.event_cost_center, parent_cc)

    def test_auto_cost_center_creates_child_on_confirm(self):
        settings = frappe.get_single("Event Settings")
        settings.auto_create_cost_center_per_event = 1
        parent_cc = frappe.db.get_value(
            "Cost Center", {"company": frappe.defaults.get_defaults().get("company"), "is_group": 0}, "name"
        )
        settings.default_cost_center = parent_cc
        settings.save(ignore_permissions=True)

        eb = self._make_event()
        self.assertFalse(eb.event_cost_center)

        eb.booking_status = "Confirmed"
        eb.save(ignore_permissions=True)

        self.assertTrue(eb.event_cost_center)
        self.assertIn(eb.name, eb.event_cost_center)

        cc = frappe.get_doc("Cost Center", eb.event_cost_center)
        self.assertEqual(cc.is_event_cost_center, 1)
        self.assertEqual(cc.parent_cost_center, parent_cc)

    def test_naming_series_format(self):
        eb = self._make_event()
        self.assertTrue(eb.name.startswith("EVT-"), f"Name {eb.name} should start with EVT-")
