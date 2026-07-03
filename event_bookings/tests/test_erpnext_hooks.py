import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from event_bookings.utils.erpnext_hooks import (
	on_quotation_cancel,
	on_quotation_submit,
	on_quotation_update,
	on_sales_invoice_cancel,
	on_sales_invoice_submit,
	on_sales_order_cancel,
	on_sales_order_submit,
	on_shift_assignment_update,
)


def _eb(docstatus=0):
	"""Minimal Event Booking stand-in returned by the mocked frappe.get_doc."""
	return SimpleNamespace(docstatus=docstatus, save=MagicMock())


# _update_linked_event_booking persists the link via frappe.db.set_value first
# (so it survives even if a later save() is blocked), then re-loads the booking
# and, for drafts, saves it.  These tests assert that contract.


@patch("event_bookings.utils.erpnext_hooks.frappe")
class TestLinkOnSubmit(unittest.TestCase):
	def test_quotation_submit_sets_link(self, mock_frappe):
		mock_frappe.get_doc.return_value = _eb(docstatus=0)
		doc = SimpleNamespace(event_booking="EVT-001", name="QTN-001", doctype="Quotation")
		on_quotation_submit(doc, "on_submit")
		mock_frappe.db.set_value.assert_called_once_with(
			"Event Booking", "EVT-001", "quotation", "QTN-001", update_modified=False
		)

	def test_sales_order_submit_sets_link(self, mock_frappe):
		mock_frappe.get_doc.return_value = _eb(docstatus=0)
		doc = SimpleNamespace(event_booking="EVT-001", name="SO-001", doctype="Sales Order")
		on_sales_order_submit(doc, "on_submit")
		mock_frappe.db.set_value.assert_called_once_with(
			"Event Booking", "EVT-001", "sales_order", "SO-001", update_modified=False
		)

	def test_sales_invoice_submit_sets_link(self, mock_frappe):
		mock_frappe.get_doc.return_value = _eb(docstatus=0)
		doc = SimpleNamespace(event_booking="EVT-001", name="SINV-001", doctype="Sales Invoice")
		on_sales_invoice_submit(doc, "on_submit")
		mock_frappe.db.set_value.assert_called_once_with(
			"Event Booking", "EVT-001", "sales_invoice", "SINV-001", update_modified=False
		)

	def test_skips_when_no_event_booking(self, mock_frappe):
		doc = SimpleNamespace(event_booking=None, name="QTN-002", doctype="Quotation")
		on_quotation_submit(doc, "on_submit")
		mock_frappe.db.set_value.assert_not_called()
		mock_frappe.get_doc.assert_not_called()


@patch("event_bookings.utils.erpnext_hooks.frappe")
class TestOnUpdate(unittest.TestCase):
	def test_quotation_update_sets_link_when_booking_present(self, mock_frappe):
		mock_frappe.get_doc.return_value = _eb(docstatus=0)
		doc = SimpleNamespace(event_booking="EVT-001", name="QTN-001", doctype="Quotation")
		on_quotation_update(doc, "on_update")
		mock_frappe.db.set_value.assert_called_once_with(
			"Event Booking", "EVT-001", "quotation", "QTN-001", update_modified=False
		)

	def test_update_noop_without_booking(self, mock_frappe):
		doc = SimpleNamespace(event_booking=None, name="QTN-002", doctype="Quotation")
		on_quotation_update(doc, "on_update")
		mock_frappe.db.set_value.assert_not_called()


@patch("event_bookings.utils.erpnext_hooks.frappe")
class TestCancelHooks(unittest.TestCase):
	def test_quotation_cancel_unlinks(self, mock_frappe):
		mock_frappe.get_doc.return_value = _eb(docstatus=0)
		doc = SimpleNamespace(event_booking="EVT-001", name="QTN-001", doctype="Quotation")
		on_quotation_cancel(doc, "on_cancel")
		mock_frappe.db.set_value.assert_called_once_with(
			"Event Booking", "EVT-001", "quotation", None, update_modified=False
		)

	def test_sales_order_cancel_unlinks(self, mock_frappe):
		mock_frappe.get_doc.return_value = _eb(docstatus=0)
		doc = SimpleNamespace(event_booking="EVT-001", name="SO-001", doctype="Sales Order")
		on_sales_order_cancel(doc, "on_cancel")
		mock_frappe.db.set_value.assert_called_once_with(
			"Event Booking", "EVT-001", "sales_order", None, update_modified=False
		)

	def test_sales_invoice_cancel_unlinks(self, mock_frappe):
		mock_frappe.get_doc.return_value = _eb(docstatus=0)
		doc = SimpleNamespace(event_booking="EVT-001", name="SINV-001", doctype="Sales Invoice")
		on_sales_invoice_cancel(doc, "on_cancel")
		mock_frappe.db.set_value.assert_called_once_with(
			"Event Booking", "EVT-001", "sales_invoice", None, update_modified=False
		)


@patch("event_bookings.utils.erpnext_hooks.frappe")
class TestShiftAssignmentUpdate(unittest.TestCase):
	def test_recomputes_when_booking_present(self, mock_frappe):
		doc = SimpleNamespace(event_booking="EVT-001", name="HR-SA-001")
		on_shift_assignment_update(doc, "on_update")
		mock_frappe.db.sql.assert_called_once()
		args = mock_frappe.db.sql.call_args[0]
		self.assertIn("tabEvent Staff Requirement", args[0])
		self.assertEqual(args[1], {"booking": "EVT-001"})

	def test_noop_without_booking(self, mock_frappe):
		doc = SimpleNamespace(event_booking=None, name="HR-SA-002")
		on_shift_assignment_update(doc, "on_update")
		mock_frappe.db.sql.assert_not_called()


if __name__ == "__main__":
	unittest.main()
