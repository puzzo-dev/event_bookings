"""Unit tests for whitelisted API functions in event_booking.py."""

import unittest
from unittest.mock import MagicMock, patch

from event_bookings.event_bookings.doctype.event_booking.event_booking import (
	get_items_from_quotation,
	get_items_from_sales_order,
)


# ── get_items_from_quotation ────────────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestGetItemsFromQuotation(unittest.TestCase):
	def _make_item(self, **kwargs):
		defaults = dict(
			item_code="ITEM-001",
			item_name="Test Item",
			qty=2,
			uom="Nos",
			rate=500.0,
			amount=1000.0,
		)
		defaults.update(kwargs)
		return MagicMock(**defaults)

	def test_returns_empty_list_for_none(self, mock_frappe):
		result = get_items_from_quotation(None)
		self.assertEqual(result, [])
		mock_frappe.get_doc.assert_not_called()
		mock_frappe.has_permission.assert_not_called()

	def test_returns_empty_list_for_empty_string(self, mock_frappe):
		result = get_items_from_quotation("")
		self.assertEqual(result, [])
		mock_frappe.get_doc.assert_not_called()

	def test_throws_when_no_read_permission(self, mock_frappe):
		mock_frappe.has_permission.return_value = False

		get_items_from_quotation("QTN-001")

		mock_frappe.has_permission.assert_called_once_with("Quotation", "read", "QTN-001")
		mock_frappe.throw.assert_called_once()
		mock_frappe.get_doc.assert_not_called()

	def test_returns_items_when_permitted(self, mock_frappe):
		mock_frappe.has_permission.return_value = True
		item = self._make_item()
		mock_qt = MagicMock()
		mock_qt.items = [item]
		mock_frappe.get_doc.return_value = mock_qt

		result = get_items_from_quotation("QTN-001")

		mock_frappe.has_permission.assert_called_once_with("Quotation", "read", "QTN-001")
		mock_frappe.get_doc.assert_called_once_with("Quotation", "QTN-001")
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["item_code"], "ITEM-001")
		self.assertEqual(result[0]["qty"], 2)
		self.assertEqual(result[0]["rate"], 500.0)

	def test_maps_all_expected_fields(self, mock_frappe):
		mock_frappe.has_permission.return_value = True
		item = self._make_item(item_code="X", item_name="Y", qty=3, uom="Box", rate=10.0, amount=30.0)
		mock_qt = MagicMock()
		mock_qt.items = [item]
		mock_frappe.get_doc.return_value = mock_qt

		result = get_items_from_quotation("QTN-001")

		row = result[0]
		self.assertEqual(set(row.keys()), {"item_code", "item_name", "qty", "uom", "rate", "amount"})
		self.assertEqual(row["amount"], 30.0)

	def test_returns_multiple_items(self, mock_frappe):
		mock_frappe.has_permission.return_value = True
		mock_qt = MagicMock()
		mock_qt.items = [self._make_item(), self._make_item(item_code="ITEM-002")]
		mock_frappe.get_doc.return_value = mock_qt

		result = get_items_from_quotation("QTN-001")
		self.assertEqual(len(result), 2)


# ── get_items_from_sales_order ──────────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestGetItemsFromSalesOrder(unittest.TestCase):
	def _make_item(self, **kwargs):
		defaults = dict(
			item_code="ITEM-001",
			item_name="Test Item",
			qty=1,
			uom="Nos",
			rate=1000.0,
			amount=1000.0,
		)
		defaults.update(kwargs)
		return MagicMock(**defaults)

	def test_returns_empty_list_for_none(self, mock_frappe):
		result = get_items_from_sales_order(None)
		self.assertEqual(result, [])
		mock_frappe.get_doc.assert_not_called()

	def test_throws_when_no_read_permission(self, mock_frappe):
		mock_frappe.has_permission.return_value = False

		get_items_from_sales_order("SO-001")

		mock_frappe.has_permission.assert_called_once_with("Sales Order", "read", "SO-001")
		mock_frappe.throw.assert_called_once()
		mock_frappe.get_doc.assert_not_called()

	def test_returns_items_when_permitted(self, mock_frappe):
		mock_frappe.has_permission.return_value = True
		item = self._make_item(item_code="SO-ITEM", qty=5)
		mock_so = MagicMock()
		mock_so.items = [item]
		mock_frappe.get_doc.return_value = mock_so

		result = get_items_from_sales_order("SO-001")

		mock_frappe.has_permission.assert_called_once_with("Sales Order", "read", "SO-001")
		mock_frappe.get_doc.assert_called_once_with("Sales Order", "SO-001")
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["item_code"], "SO-ITEM")
		self.assertEqual(result[0]["qty"], 5)

	def test_maps_all_expected_fields(self, mock_frappe):
		mock_frappe.has_permission.return_value = True
		item = self._make_item(item_code="A", item_name="B", qty=2, uom="Pcs", rate=50.0, amount=100.0)
		mock_so = MagicMock()
		mock_so.items = [item]
		mock_frappe.get_doc.return_value = mock_so

		result = get_items_from_sales_order("SO-001")

		row = result[0]
		self.assertEqual(set(row.keys()), {"item_code", "item_name", "qty", "uom", "rate", "amount"})
