"""S-5 — Event Booking Settings defaults flow through the consumers that
read them, and blank settings fall back to pre-settings behaviour.

Covers the two settings that survive (customer naming is ERPNext Selling
Settings' job — see the cancelled S-3):
- default_customer_group  (Lead → Customer conversion)
- default_warehouse       (Create Stock Entry prefill)
"""

import unittest

import frappe
from event_bookings.tests.compat import FrappeTestCase

from event_bookings.event_bookings.doctype.event_booking.event_booking import (
	make_stock_entry,
)
from event_bookings.tests.fixtures import (
	ensure_test_customer_leaf_details,
	get_or_create_test_customer,
	get_or_create_test_event_type,
)
from event_bookings.utils.erpnext_bridge import make_customer_from_lead

ERPNEXT_INSTALLED = "erpnext" in frappe.get_installed_apps()


def _set_settings(**values):
	frappe.db.set_value(
		"Event Booking Settings", "Event Booking Settings", values, update_modified=False
	)


def _get_or_create_test_lead(lead_name="Test Settings Lead"):
	existing = frappe.db.get_value("Lead", {"lead_name": lead_name}, "name")
	if existing:
		return existing
	return frappe.get_doc({"doctype": "Lead", "lead_name": lead_name}).insert(
		ignore_permissions=True
	).name


class TestSettingsBase(FrappeTestCase):
	def setUp(self):
		_set_settings(
			default_customer_group=None,
			default_warehouse=None,
		)

	def tearDown(self):
		frappe.db.rollback()


@unittest.skipUnless(ERPNEXT_INSTALLED, "settings consumers require ERPNext")
class TestDefaultCustomerGroup(TestSettingsBase):
	def test_settings_group_takes_priority(self):
		group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		_set_settings(default_customer_group=group)

		lead = _get_or_create_test_lead()
		customer = make_customer_from_lead(lead)

		self.assertEqual(customer.customer_group, group)

	def test_blank_falls_back_to_site_default(self):
		lead = _get_or_create_test_lead()
		customer = make_customer_from_lead(lead)

		expected = (
			frappe.db.get_default("customer_group")
			or frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
			or "All Customer Groups"
		)
		self.assertEqual(customer.customer_group, expected)


@unittest.skipUnless(ERPNEXT_INSTALLED, "settings consumers require ERPNext")
class TestDefaultWarehouse(TestSettingsBase):
	def setUp(self):
		super().setUp()
		ensure_test_customer_leaf_details()
		self.customer = get_or_create_test_customer()
		self.event_type = get_or_create_test_event_type()

	def _make_booking(self):
		return frappe.get_doc(
			{
				"doctype": "Event Booking",
				"event_name": "Settings Warehouse Booking",
				"event_type": self.event_type,
				"booking_status": "Confirmed",
				"booking_date": frappe.utils.today(),
				"event_date": frappe.utils.add_days(frappe.utils.today(), 30),
				"event_time": "18:00:00",
				"event_location": "Test Hall",
				"customer": self.customer,
				"company": frappe.db.get_value("Company", {}, "name", order_by="creation asc"),
			}
		).insert(ignore_permissions=True)

	def test_warehouse_prefilled_on_stock_entry(self):
		warehouse = frappe.db.get_value(
			"Warehouse", {"is_group": 0, "disabled": 0}, "name"
		)
		_set_settings(default_warehouse=warehouse)

		booking = self._make_booking()
		se = frappe._dict(make_stock_entry(booking.name, "Material Issue"))

		self.assertEqual(se.from_warehouse, warehouse)
		self.assertEqual(se.to_warehouse, warehouse)
		self.assertEqual(se.event_booking, booking.name)
		self.assertEqual(se.stock_entry_type, "Material Issue")

	def test_blank_settings_leave_warehouses_unset(self):
		booking = self._make_booking()
		se = frappe._dict(make_stock_entry(booking.name, "Material Issue"))

		self.assertIsNone(se.from_warehouse)
		self.assertIsNone(se.to_warehouse)
		self.assertEqual(se.event_booking, booking.name)
