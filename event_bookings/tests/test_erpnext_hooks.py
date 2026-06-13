import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from event_bookings.utils.erpnext_hooks import (
	on_quotation_submit,
	on_sales_invoice_submit,
	on_sales_order_submit,
	on_shift_assignment_update,
	on_stock_entry_submit,
)


class _FakeEB:
	"""Minimal stand-in for an Event Booking document."""

	def __init__(self):
		self.quotation = None
		self.sales_order = None
		self.sales_invoice = None
		self.total_actual = None

	def save(self, **kwargs):
		self._saved = True

	def update_staff_assignment_counts(self):
		self._staff_updated = True


@patch("event_bookings.utils.erpnext_hooks.frappe")
class TestOnQuotationSubmit(unittest.TestCase):
	def test_links_quotation_to_booking(self, mock_frappe):
		eb = _FakeEB()
		mock_frappe.get_doc.return_value = eb

		doc = SimpleNamespace(event_booking="EVT-001", name="QTN-001")
		on_quotation_submit(doc, "on_submit")

		mock_frappe.get_doc.assert_called_once_with("Event Booking", "EVT-001")
		self.assertEqual(eb.quotation, "QTN-001")

	def test_skips_when_no_event_booking(self, mock_frappe):
		doc = SimpleNamespace(event_booking=None, name="QTN-002")
		on_quotation_submit(doc, "on_submit")
		mock_frappe.get_doc.assert_not_called()


@patch("event_bookings.utils.erpnext_hooks.frappe")
class TestOnSalesOrderSubmit(unittest.TestCase):
	def test_links_sales_order_and_sets_total(self, mock_frappe):
		eb = _FakeEB()
		mock_frappe.get_doc.return_value = eb

		doc = SimpleNamespace(event_booking="EVT-001", name="SO-001", grand_total=75000)
		on_sales_order_submit(doc, "on_submit")

		self.assertEqual(eb.sales_order, "SO-001")
		self.assertEqual(eb.total_actual, 75000)

	def test_skips_when_no_event_booking(self, mock_frappe):
		doc = SimpleNamespace(event_booking="", name="SO-002", grand_total=0)
		on_sales_order_submit(doc, "on_submit")
		mock_frappe.get_doc.assert_not_called()


@patch("event_bookings.utils.erpnext_hooks.frappe")
class TestOnSalesInvoiceSubmit(unittest.TestCase):
	def test_links_invoice_to_booking(self, mock_frappe):
		eb = _FakeEB()
		mock_frappe.get_doc.return_value = eb

		doc = SimpleNamespace(event_booking="EVT-001", name="SINV-001")
		on_sales_invoice_submit(doc, "on_submit")

		self.assertEqual(eb.sales_invoice, "SINV-001")

	def test_skips_when_no_event_booking(self, mock_frappe):
		doc = SimpleNamespace(event_booking=None, name="SINV-002")
		on_sales_invoice_submit(doc, "on_submit")
		mock_frappe.get_doc.assert_not_called()


@patch("event_bookings.utils.erpnext_hooks.frappe")
class TestOnStockEntrySubmit(unittest.TestCase):
	def test_saves_booking_on_material_issue(self, mock_frappe):
		eb = _FakeEB()
		mock_frappe.get_doc.return_value = eb

		doc = SimpleNamespace(
			event_booking="EVT-001",
			stock_entry_type="Material Issue",
			name="STE-001",
		)
		on_stock_entry_submit(doc, "on_submit")

		mock_frappe.get_doc.assert_called_once_with("Event Booking", "EVT-001")
		self.assertTrue(eb._saved)

	def test_skips_non_material_issue(self, mock_frappe):
		doc = SimpleNamespace(
			event_booking="EVT-001",
			stock_entry_type="Material Receipt",
			name="STE-002",
		)
		on_stock_entry_submit(doc, "on_submit")
		mock_frappe.get_doc.assert_not_called()

	def test_skips_when_no_event_booking(self, mock_frappe):
		doc = SimpleNamespace(
			event_booking=None,
			stock_entry_type="Material Issue",
			name="STE-003",
		)
		on_stock_entry_submit(doc, "on_submit")
		mock_frappe.get_doc.assert_not_called()


@patch("event_bookings.utils.erpnext_hooks.frappe")
class TestOnShiftAssignmentUpdate(unittest.TestCase):
	def test_updates_staff_counts(self, mock_frappe):
		eb = _FakeEB()
		mock_frappe.get_doc.return_value = eb

		doc = SimpleNamespace(event_booking="EVT-001")
		on_shift_assignment_update(doc, "on_update")

		self.assertTrue(eb._staff_updated)
		self.assertTrue(eb._saved)

	def test_skips_when_no_event_booking(self, mock_frappe):
		doc = SimpleNamespace(event_booking="")
		on_shift_assignment_update(doc, "on_update")
		mock_frappe.get_doc.assert_not_called()
