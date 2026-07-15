import unittest
from unittest.mock import patch

from event_bookings.event_bookings.report.event_booking_profitability.event_booking_profitability import (
	execute,
	get_columns,
	get_data,
)
from frappe import _dict


class TestGetColumns(unittest.TestCase):
	def test_returns_expected_column_count(self):
		cols = get_columns()
		self.assertEqual(len(cols), 13)

	def test_column_fieldnames(self):
		cols = get_columns()
		names = [c["fieldname"] for c in cols]
		expected = [
			"event_name",
			"party_type",
			"party_name",
			"event_date",
			"event_time",
			"booking_status",
			"total_estimated",
			"total_actual",
			"cogs",
			"damages_cost",
			"net_profit",
			"margin_pct",
			"revenue_type",
		]
		self.assertEqual(names, expected)

	def test_currency_columns_have_correct_fieldtype(self):
		cols = get_columns()
		currency_fields = {"total_estimated", "total_actual", "cogs", "damages_cost", "net_profit"}
		for col in cols:
			if col["fieldname"] in currency_fields:
				self.assertEqual(col["fieldtype"], "Currency", f"{col['fieldname']} should be Currency")


_MODULE = "event_bookings.event_bookings.report.event_booking_profitability.event_booking_profitability"


@patch(f"{_MODULE}._get_damages_map", return_value={})
@patch(f"{_MODULE}._get_cogs_map", return_value={})
@patch(f"{_MODULE}.frappe")
class TestGetData(unittest.TestCase):
	def _make_booking(self, **overrides):
		row = _dict(
			event_name="EVT-001",
			party_type="Customer",
			party_name="Acme",
			event_date="2026-07-15",
			booking_status="Invoiced",
			total_estimated=50000,
			total_actual=60000,
		)
		row.update(overrides)
		return row

	def test_profit_calculated_from_actual_revenue(self, mock_frappe, _mock_cogs, mock_damages):
		mock_frappe.get_list.return_value = [self._make_booking()]
		mock_damages.return_value = {"EVT-001": 5000}
		data = get_data({})

		self.assertEqual(len(data), 1)
		self.assertEqual(data[0]["net_profit"], 55000)  # 60000 - 5000

	def test_uses_estimated_when_no_actual(self, mock_frappe, _mock_cogs, _mock_damages):
		mock_frappe.get_list.return_value = [
			self._make_booking(total_actual=0, total_estimated=40000)
		]
		data = get_data({})
		self.assertEqual(data[0]["net_profit"], 40000)

	def test_revenue_type_actual(self, mock_frappe, _mock_cogs, _mock_damages):
		mock_frappe.get_list.return_value = [self._make_booking(total_actual=60000)]
		data = get_data({})
		self.assertEqual(data[0]["revenue_type"], "Actual")

	def test_revenue_type_estimated(self, mock_frappe, _mock_cogs, _mock_damages):
		mock_frappe.get_list.return_value = [self._make_booking(total_actual=0, total_estimated=40000)]
		data = get_data({})
		self.assertEqual(data[0]["revenue_type"], "Estimated")

	def test_margin_percentage(self, mock_frappe, _mock_cogs, mock_damages):
		mock_frappe.get_list.return_value = [self._make_booking(total_actual=100000)]
		mock_damages.return_value = {"EVT-001": 20000}
		data = get_data({})
		self.assertAlmostEqual(data[0]["margin_pct"], 80.0)

	def test_zero_revenue_margin(self, mock_frappe, _mock_cogs, _mock_damages):
		mock_frappe.get_list.return_value = [
			self._make_booking(total_actual=0, total_estimated=0)
		]
		data = get_data({})
		self.assertEqual(data[0]["margin_pct"], 0)

	def test_cogs_defaults_to_zero(self, mock_frappe, _mock_cogs, _mock_damages):
		mock_frappe.get_list.return_value = [self._make_booking()]
		data = get_data({})
		self.assertEqual(data[0]["cogs"], 0)

	def test_damages_defaults_to_zero(self, mock_frappe, _mock_cogs, _mock_damages):
		mock_frappe.get_list.return_value = [self._make_booking()]
		data = get_data({})
		self.assertEqual(data[0]["damages_cost"], 0)

	def test_filter_by_party_name(self, mock_frappe, _mock_cogs, _mock_damages):
		mock_frappe.get_list.return_value = []
		get_data({"party_name": "Acme"})
		call_kwargs = mock_frappe.get_list.call_args
		self.assertEqual(call_kwargs[1]["filters"]["party_name"], "Acme")

	def test_filter_by_party_type(self, mock_frappe, _mock_cogs, _mock_damages):
		mock_frappe.get_list.return_value = []
		get_data({"party_type": "Customer"})
		call_kwargs = mock_frappe.get_list.call_args
		self.assertEqual(call_kwargs[1]["filters"]["party_type"], "Customer")

	def test_filter_by_event_type(self, mock_frappe, _mock_cogs, _mock_damages):
		mock_frappe.get_list.return_value = []
		get_data({"event_type": "Wedding"})
		call_kwargs = mock_frappe.get_list.call_args
		self.assertEqual(call_kwargs[1]["filters"]["event_type"], "Wedding")

	def test_filter_by_status(self, mock_frappe, _mock_cogs, _mock_damages):
		mock_frappe.get_list.return_value = []
		get_data({"booking_status": "Paid"})
		call_kwargs = mock_frappe.get_list.call_args
		self.assertEqual(call_kwargs[1]["filters"]["booking_status"], "Paid")

	def test_filter_by_date_range(self, mock_frappe, _mock_cogs, _mock_damages):
		mock_frappe.get_list.return_value = []
		get_data({"from_date": "2026-01-01", "to_date": "2026-12-31"})
		call_kwargs = mock_frappe.get_list.call_args
		self.assertIn("event_date", call_kwargs[1]["filters"])

	def test_empty_filters(self, mock_frappe, _mock_cogs, _mock_damages):
		mock_frappe.get_list.return_value = []
		data = get_data({})
		self.assertEqual(data, [])


@patch(f"{_MODULE}.frappe")
class TestExecute(unittest.TestCase):
	def test_returns_columns_and_data(self, mock_frappe):
		mock_frappe.get_list.return_value = []
		columns, data = execute()
		self.assertEqual(len(columns), 13)
		self.assertIsInstance(data, list)

	def test_none_filters_treated_as_empty(self, mock_frappe):
		mock_frappe.get_list.return_value = []
		columns, _data = execute(filters=None)
		self.assertEqual(len(columns), 13)
