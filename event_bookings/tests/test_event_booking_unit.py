"""Unit tests for EventBooking methods not covered by the integration tests.

These tests mock frappe so they can run without a live Frappe site.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from event_bookings.event_bookings.doctype.event_booking.event_booking import EventBooking


def _make_staff_req(**overrides):
	defaults = {
		"designation": "Waiter",
		"qty_required": 3,
	}
	defaults.update(overrides)
	return defaults


def _new_booking(**overrides):
	"""Create a bare EventBooking instance without calling __init__."""
	eb = object.__new__(EventBooking)
	eb.staff_requirements = []
	eb.event_cost_center = None
	eb.total_estimated = 0
	eb.total_actual = 0
	eb.quotation = None
	eb.sales_order = None
	eb.sales_invoice = None
	eb.material_request = None
	eb.booking_status = "New"
	eb.customer = "Test Customer"
	eb.event_name = "Test Event"
	eb.event_date = "2026-08-01"
	eb.event_time = "18:00:00"
	eb.event_timing = "2026-08-01 18:00:00"
	eb.event_location = "Venue"
	eb.name = "EVT-001"
	eb.flags = SimpleNamespace(ignore_permissions=False)
	for k, v in overrides.items():
		setattr(eb, k, v)
	return eb


# ── calculate_totals ────────────────────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestCalculateTotals(unittest.TestCase):
	def test_no_linked_docs(self, mock_frappe):
		mock_frappe.db.get_value.return_value = None
		eb = _new_booking()
		eb.calculate_totals()
		self.assertEqual(eb.total_estimated, 0.0)
		self.assertEqual(eb.total_actual, 0.0)

	def test_from_quotation(self, mock_frappe):
		mock_frappe.db.get_value.return_value = 2500.0
		eb = _new_booking(quotation="QTN-001")
		eb.calculate_totals()
		self.assertEqual(eb.total_estimated, 2500.0)
		self.assertEqual(eb.total_actual, 0.0)

	def test_from_sales_order(self, mock_frappe):
		mock_frappe.db.get_value.side_effect = [2500.0, 3000.0]
		eb = _new_booking(quotation="QTN-001", sales_order="SO-001")
		eb.calculate_totals()
		self.assertEqual(eb.total_estimated, 2500.0)
		self.assertEqual(eb.total_actual, 3000.0)

	def test_from_sales_invoice_when_no_so(self, mock_frappe):
		mock_frappe.db.get_value.return_value = 4500.0
		eb = _new_booking(sales_invoice="SI-001")
		eb.calculate_totals()
		self.assertEqual(eb.total_estimated, 0.0)
		self.assertEqual(eb.total_actual, 4500.0)

	def test_planner_commission_from_actual(self, mock_frappe):
		mock_frappe.db.get_value.side_effect = [10000.0, 10.0]
		eb = _new_booking(
			sales_order="SO-001",
			event_planner="Planner-1",
		)
		eb.calculate_totals()
		self.assertEqual(eb.event_planner_commission_amount, 1000.0)

	def test_planner_commission_from_estimated(self, mock_frappe):
		mock_frappe.db.get_value.side_effect = [5000.0, 0.0, 5.0]
		eb = _new_booking(
			quotation="QTN-001",
			event_planner="Planner-1",
		)
		eb.calculate_totals()
		self.assertEqual(eb.event_planner_commission_amount, 250.0)


# ── validate_dates ──────────────────────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.today")
class TestValidateDates(unittest.TestCase):
	def test_past_date_new_booking_throws(self, mock_today, mock_frappe):
		mock_today.return_value = "2026-07-10"
		eb = _new_booking(event_timing="2026-07-09 18:00:00")
		eb.is_new = lambda: True

		eb.validate_dates()
		mock_frappe.throw.assert_called_once()

	def test_past_date_existing_booking_no_throw(self, mock_today, mock_frappe):
		mock_today.return_value = "2026-07-10"
		eb = _new_booking(event_timing="2026-07-09 18:00:00")
		eb.is_new = lambda: False

		eb.validate_dates()
		mock_frappe.throw.assert_not_called()

	def test_future_date_no_throw(self, mock_today, mock_frappe):
		mock_today.return_value = "2026-07-10"
		eb = _new_booking(event_timing="2026-07-15 18:00:00")
		eb.is_new = lambda: True

		eb.validate_dates()
		mock_frappe.throw.assert_not_called()

	def test_none_date_no_throw(self, mock_today, mock_frappe):
		eb = _new_booking(event_timing=None)
		eb.is_new = lambda: True

		eb.validate_dates()
		mock_frappe.throw.assert_not_called()

	def test_end_time_before_timing_throws(self, mock_today, mock_frappe):
		eb = _new_booking(event_timing="2026-08-01 18:00:00", event_end_datetime="2026-08-01 12:00:00")
		eb.validate_dates()
		mock_frappe.throw.assert_called_once()

	def test_end_time_equal_timing_throws(self, mock_today, mock_frappe):
		eb = _new_booking(event_timing="2026-08-01 18:00:00", event_end_datetime="2026-08-01 18:00:00")
		eb.validate_dates()
		mock_frappe.throw.assert_called_once()


# ── validate_review_requirement ─────────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestValidateReviewRequirement(unittest.TestCase):
	def test_review_required_blocks_invoicing(self, mock_frappe):
		settings = SimpleNamespace(require_review=True)
		mock_frappe.get_cached_doc.return_value = settings
		mock_frappe.db.exists.return_value = False

		eb = _new_booking()
		eb.validate_review_requirement()
		mock_frappe.throw.assert_called_once()

	def test_review_not_required_allows(self, mock_frappe):
		settings = SimpleNamespace(require_review=False)
		mock_frappe.get_cached_doc.return_value = settings

		eb = _new_booking()
		eb.validate_review_requirement()
		mock_frappe.throw.assert_not_called()


# ── create_quotation ────────────────────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestCreateQuotation(unittest.TestCase):
	def test_skips_when_quotation_exists(self, mock_frappe):
		eb = _new_booking(quotation="QTN-001")
		eb.create_quotation()
		mock_frappe.get_doc.assert_not_called()

	def test_builds_blank_quotation(self, mock_frappe):
		settings = SimpleNamespace(
			default_cost_center="CC-001",
			default_income_account="Income - TC",
		)
		mock_frappe.get_cached_doc.return_value = settings
		mock_frappe.db.get_value.side_effect = ["Test Co", "USD"]

		mock_qt = MagicMock()
		mock_qt.name = "QTN-NEW"
		mock_frappe.get_doc.return_value = mock_qt

		eb = _new_booking(
			customer="Acme",
			event_cost_center="CC-EVT",
			quotation=None,
		)
		eb.create_quotation()

		mock_frappe.get_doc.assert_called_once()
		call_args = mock_frappe.get_doc.call_args[0][0]
		self.assertEqual(call_args["party_name"], "Acme")
		mock_qt.db_insert.assert_called_once()
		mock_qt.reload.assert_called_once()
		self.assertEqual(eb.quotation, "QTN-NEW")
