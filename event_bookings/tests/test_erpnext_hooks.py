import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


# _sql_items_total is imported into erpnext_hooks at module level; patch it there
# so unit tests never reach the real frappe.db.sql.
_SQL_TOTAL_PATH = "event_bookings.utils.erpnext_hooks._sql_items_total"
_FRAPPE_PATH = "event_bookings.utils.erpnext_hooks.frappe"


@patch(_SQL_TOTAL_PATH, return_value=0.0)
@patch(_FRAPPE_PATH)
class TestOnQuotationSubmit(unittest.TestCase):
	def setUp(self):
		from event_bookings.utils.erpnext_hooks import on_quotation_submit
		self.fn = on_quotation_submit

	def test_sets_quotation_link_on_booking(self, mock_frappe, _sql):
		mock_frappe.db.get_value.return_value = MagicMock(
			quotation=None, sales_order=None, sales_invoice=None
		)
		doc = SimpleNamespace(event_booking="EVT-001", name="QTN-001", docstatus=1)
		self.fn(doc, "on_submit")
		mock_frappe.db.set_value.assert_called()

	def test_skips_when_no_event_booking(self, mock_frappe, _sql):
		doc = SimpleNamespace(event_booking=None, name="QTN-002", docstatus=1)
		self.fn(doc, "on_submit")
		mock_frappe.db.set_value.assert_not_called()


@patch(_SQL_TOTAL_PATH, return_value=0.0)
@patch(_FRAPPE_PATH)
class TestOnSalesOrderSubmit(unittest.TestCase):
	def setUp(self):
		from event_bookings.utils.erpnext_hooks import on_sales_order_submit
		self.fn = on_sales_order_submit

	def test_sets_sales_order_link_on_booking(self, mock_frappe, _sql):
		mock_frappe.db.get_value.return_value = MagicMock(
			quotation=None, sales_order=None, sales_invoice=None
		)
		doc = SimpleNamespace(event_booking="EVT-001", name="SO-001", docstatus=1)
		self.fn(doc, "on_submit")
		mock_frappe.db.set_value.assert_called()

	def test_skips_when_no_event_booking(self, mock_frappe, _sql):
		doc = SimpleNamespace(event_booking="", name="SO-002", docstatus=1)
		self.fn(doc, "on_submit")
		mock_frappe.db.set_value.assert_not_called()


@patch(_SQL_TOTAL_PATH, return_value=0.0)
@patch(_FRAPPE_PATH)
class TestOnSalesInvoiceSubmit(unittest.TestCase):
	def setUp(self):
		from event_bookings.utils.erpnext_hooks import on_sales_invoice_submit
		self.fn = on_sales_invoice_submit

	def test_sets_invoice_link_on_booking(self, mock_frappe, _sql):
		mock_frappe.db.get_value.return_value = MagicMock(
			quotation=None, sales_order=None, sales_invoice=None
		)
		doc = SimpleNamespace(event_booking="EVT-001", name="SINV-001", docstatus=1)
		self.fn(doc, "on_submit")
		mock_frappe.db.set_value.assert_called()

	def test_skips_when_no_event_booking(self, mock_frappe, _sql):
		doc = SimpleNamespace(event_booking=None, name="SINV-002", docstatus=1)
		self.fn(doc, "on_submit")
		mock_frappe.db.set_value.assert_not_called()


@patch(_FRAPPE_PATH)
class TestOnShiftAssignmentUpdate(unittest.TestCase):
	def setUp(self):
		from event_bookings.utils.erpnext_hooks import on_shift_assignment_update
		self.fn = on_shift_assignment_update

	def test_executes_sql_update_join(self, mock_frappe):
		"""Shift assignment update must fire a single SQL UPDATE JOIN — no doc load."""
		doc = SimpleNamespace(event_booking="EVT-001")
		self.fn(doc, "on_update")
		mock_frappe.db.sql.assert_called_once()
		sql_arg = mock_frappe.db.sql.call_args[0][0]
		self.assertIn("tabEvent Staff Requirement", sql_arg)
		self.assertIn("tabShift Assignment", sql_arg)

	def test_skips_when_no_event_booking(self, mock_frappe):
		doc = SimpleNamespace(event_booking="")
		self.fn(doc, "on_update")
		mock_frappe.db.sql.assert_not_called()

	def test_logs_error_on_sql_failure(self, mock_frappe):
		mock_frappe.db.sql.side_effect = Exception("DB error")
		doc = SimpleNamespace(event_booking="EVT-002")
		self.fn(doc, "on_update")
		mock_frappe.log_error.assert_called_once()
