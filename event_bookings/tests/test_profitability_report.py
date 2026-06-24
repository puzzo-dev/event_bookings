import unittest
from unittest.mock import MagicMock, patch

from frappe import _dict

_REPORT_MODULE = "event_bookings.report.event_booking_profitability.event_booking_profitability"


class TestGetColumns(unittest.TestCase):
	@patch(f"{_REPORT_MODULE}._", side_effect=lambda x: x)
	def test_returns_expected_column_count(self, _):
		from event_bookings.report.event_booking_profitability.event_booking_profitability import get_columns
		cols = get_columns()
		self.assertEqual(len(cols), 9)

	@patch(f"{_REPORT_MODULE}._", side_effect=lambda x: x)
	def test_column_fieldnames(self, _):
		from event_bookings.report.event_booking_profitability.event_booking_profitability import get_columns
		cols = get_columns()
		names = [c["fieldname"] for c in cols]
		expected = [
			"event_name",
			"customer",
			"event_timing",
			"booking_status",
			"total_estimated",
			"total_actual",
			"cogs",
			"net_profit",
			"margin_pct",
		]
		self.assertEqual(names, expected)

	@patch(f"{_REPORT_MODULE}._", side_effect=lambda x: x)
	def test_currency_columns_have_correct_fieldtype(self, _):
		from event_bookings.report.event_booking_profitability.event_booking_profitability import get_columns
		cols = get_columns()
		currency_fields = {"total_estimated", "total_actual", "cogs", "net_profit"}
		for col in cols:
			if col["fieldname"] in currency_fields:
				self.assertEqual(col["fieldtype"], "Currency", f"{col['fieldname']} should be Currency")


def _make_booking(**overrides):
	row = _dict(
		event_name="EVT-001",
		customer="Acme",
		event_timing="2026-07-15 18:00:00",
		booking_status="Invoiced",
		total_estimated=50000,
		total_actual=60000,
	)
	row.update(overrides)
	return row


@patch(f"{_REPORT_MODULE}._", side_effect=lambda x: x)
@patch(f"{_REPORT_MODULE}.frappe")
class TestGetData(unittest.TestCase):
	def _setup_cache_miss(self, mock_frappe):
		cache_obj = MagicMock()
		cache_obj.get.return_value = None
		mock_frappe.cache.return_value = cache_obj
		return cache_obj

	def test_profit_calculated_from_actual_revenue(self, mock_frappe, _):
		cache = self._setup_cache_miss(mock_frappe)
		mock_frappe.get_all.return_value = [_make_booking()]
		mock_frappe.db.sql.return_value = []

		from event_bookings.report.event_booking_profitability.event_booking_profitability import get_data
		data = get_data({})

		self.assertEqual(len(data), 1)
		self.assertEqual(data[0]["net_profit"], 60000)  # 60000 actual - 0 cogs

	def test_uses_estimated_when_no_actual(self, mock_frappe, _):
		self._setup_cache_miss(mock_frappe)
		mock_frappe.get_all.return_value = [_make_booking(total_actual=0, total_estimated=40000)]
		mock_frappe.db.sql.return_value = []

		from event_bookings.report.event_booking_profitability.event_booking_profitability import get_data
		data = get_data({})
		self.assertEqual(data[0]["net_profit"], 40000)

	def test_margin_percentage(self, mock_frappe, _):
		self._setup_cache_miss(mock_frappe)
		mock_frappe.get_all.return_value = [_make_booking(total_actual=100000)]
		mock_frappe.db.sql.return_value = [["EVT-001", 20000]]  # COGS row

		from event_bookings.report.event_booking_profitability.event_booking_profitability import get_data
		data = get_data({})
		self.assertAlmostEqual(data[0]["margin_pct"], 80.0)

	def test_zero_revenue_margin(self, mock_frappe, _):
		self._setup_cache_miss(mock_frappe)
		mock_frappe.get_all.return_value = [_make_booking(total_actual=0, total_estimated=0)]
		mock_frappe.db.sql.return_value = []

		from event_bookings.report.event_booking_profitability.event_booking_profitability import get_data
		data = get_data({})
		self.assertEqual(data[0]["margin_pct"], 0)

	def test_cogs_defaults_to_zero(self, mock_frappe, _):
		self._setup_cache_miss(mock_frappe)
		mock_frappe.get_all.return_value = [_make_booking()]
		mock_frappe.db.sql.return_value = []

		from event_bookings.report.event_booking_profitability.event_booking_profitability import get_data
		data = get_data({})
		self.assertEqual(data[0]["cogs"], 0)

	def test_filter_by_customer(self, mock_frappe, _):
		self._setup_cache_miss(mock_frappe)
		mock_frappe.get_all.return_value = []

		from event_bookings.report.event_booking_profitability.event_booking_profitability import get_data
		get_data({"customer": "Acme"})
		call_kwargs = mock_frappe.get_all.call_args
		self.assertEqual(call_kwargs[1]["filters"]["customer"], "Acme")

	def test_filter_by_event_type(self, mock_frappe, _):
		self._setup_cache_miss(mock_frappe)
		mock_frappe.get_all.return_value = []

		from event_bookings.report.event_booking_profitability.event_booking_profitability import get_data
		get_data({"event_type": "Wedding"})
		call_kwargs = mock_frappe.get_all.call_args
		self.assertEqual(call_kwargs[1]["filters"]["event_type"], "Wedding")

	def test_filter_by_status(self, mock_frappe, _):
		self._setup_cache_miss(mock_frappe)
		mock_frappe.get_all.return_value = []

		from event_bookings.report.event_booking_profitability.event_booking_profitability import get_data
		get_data({"booking_status": "Paid"})
		call_kwargs = mock_frappe.get_all.call_args
		self.assertEqual(call_kwargs[1]["filters"]["booking_status"], "Paid")

	def test_filter_by_date_range(self, mock_frappe, _):
		self._setup_cache_miss(mock_frappe)
		mock_frappe.get_all.return_value = []

		from event_bookings.report.event_booking_profitability.event_booking_profitability import get_data
		get_data({"from_date": "2026-01-01", "to_date": "2026-12-31"})
		call_kwargs = mock_frappe.get_all.call_args
		self.assertIn("event_timing", call_kwargs[1]["filters"])

	def test_empty_filters(self, mock_frappe, _):
		self._setup_cache_miss(mock_frappe)
		mock_frappe.get_all.return_value = []

		from event_bookings.report.event_booking_profitability.event_booking_profitability import get_data
		data = get_data({})
		self.assertEqual(data, [])


@patch(f"{_REPORT_MODULE}._", side_effect=lambda x: x)
@patch(f"{_REPORT_MODULE}.frappe")
class TestExecute(unittest.TestCase):
	def _setup_cache_miss(self, mock_frappe):
		cache_obj = MagicMock()
		cache_obj.get.return_value = None
		mock_frappe.cache.return_value = cache_obj

	def test_returns_columns_and_data(self, mock_frappe, _):
		self._setup_cache_miss(mock_frappe)
		mock_frappe.get_all.return_value = []

		from event_bookings.report.event_booking_profitability.event_booking_profitability import execute
		columns, data = execute()
		self.assertEqual(len(columns), 9)
		self.assertIsInstance(data, list)

	def test_none_filters_treated_as_empty(self, mock_frappe, _):
		self._setup_cache_miss(mock_frappe)
		mock_frappe.get_all.return_value = []

		from event_bookings.report.event_booking_profitability.event_booking_profitability import execute
		columns, _data = execute(filters=None)
		self.assertEqual(len(columns), 9)
