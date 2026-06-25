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
	eb.party_type = "Customer"
	eb.party_name = "Test Customer"
	eb.event_planner = None
	eb.event_planner_commission_amount = 0
	eb.event_name = "Test Event"
	eb.event_date = "2026-08-01"
	eb.event_time = "18:00:00"
	eb.event_timing = "2026-08-01 18:00:00"
	eb.event_location = "Venue"
	eb.name = "EVT-001"
	eb.event_end_datetime = None
	eb.event_end_date = None
	eb.event_end_time = None
	eb.company = None
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
		# quotation total → 5000, commission_rate → 5.0; SO is None so no SO call
		mock_frappe.db.get_value.side_effect = [5000.0, 5.0]
		eb = _new_booking(
			quotation="QTN-001",
			event_planner="Planner-1",
		)
		eb.calculate_totals()
		self.assertEqual(eb.event_planner_commission_amount, 250.0)


# ── validate_dates ──────────────────────────────────────────────────


_MODULE = "event_bookings.event_bookings.doctype.event_booking.event_booking"

_PAST = "2026-07-09 18:00:00"
_FUTURE = "2026-07-15 18:00:00"
_NOW = "2026-07-10 12:00:00"


@patch(f"{_MODULE}._", side_effect=lambda x: x)
@patch(f"{_MODULE}.frappe")
@patch(f"{_MODULE}.now_datetime")
class TestValidateDates(unittest.TestCase):
	def test_past_date_new_booking_throws(self, mock_now, mock_frappe, _):
		from datetime import datetime
		mock_now.return_value = datetime(2026, 7, 10, 12, 0, 0)
		eb = _new_booking(event_timing=_PAST)
		eb.is_new = lambda: True

		eb.validate_dates()
		mock_frappe.throw.assert_called_once()

	def test_past_date_existing_booking_no_throw(self, mock_now, mock_frappe, _):
		from datetime import datetime
		mock_now.return_value = datetime(2026, 7, 10, 12, 0, 0)
		eb = _new_booking(event_timing=_PAST)
		eb.is_new = lambda: False

		eb.validate_dates()
		mock_frappe.throw.assert_not_called()

	def test_future_date_no_throw(self, mock_now, mock_frappe, _):
		from datetime import datetime
		mock_now.return_value = datetime(2026, 7, 10, 12, 0, 0)
		eb = _new_booking(event_timing=_FUTURE)
		eb.is_new = lambda: True

		eb.validate_dates()
		mock_frappe.throw.assert_not_called()

	def test_none_date_no_throw(self, mock_now, mock_frappe, _):
		eb = _new_booking(event_timing=None)
		eb.is_new = lambda: True

		eb.validate_dates()
		mock_frappe.throw.assert_not_called()

	def test_end_time_before_timing_throws(self, mock_now, mock_frappe, _):
		from datetime import datetime
		mock_now.return_value = datetime(2026, 7, 1, 12, 0, 0)
		eb = _new_booking(event_timing="2026-08-01 18:00:00", event_end_datetime="2026-08-01 12:00:00")
		eb.is_new = lambda: False
		eb.validate_dates()
		mock_frappe.throw.assert_called_once()

	def test_end_time_equal_timing_throws(self, mock_now, mock_frappe, _):
		from datetime import datetime
		mock_now.return_value = datetime(2026, 7, 1, 12, 0, 0)
		eb = _new_booking(event_timing="2026-08-01 18:00:00", event_end_datetime="2026-08-01 18:00:00")
		eb.is_new = lambda: False
		eb.validate_dates()
		mock_frappe.throw.assert_called_once()


# ── validate_review_requirement ─────────────────────────────────────


@patch(f"{_MODULE}._", side_effect=lambda x: x)
@patch(f"{_MODULE}.frappe")
class TestValidateReviewRequirement(unittest.TestCase):
	def test_review_required_blocks_invoicing(self, mock_frappe, _):
		settings = SimpleNamespace(require_review=True)
		# get_settings() calls get_cached_doc("Event Booking Settings", "Event Booking Settings")
		mock_frappe.get_cached_doc.return_value = settings
		# validate_review_requirement checks frappe.db.exists("Booking Review", ...) → False
		mock_frappe.db.exists.return_value = False
		mock_frappe.throw.side_effect = Exception("review required")

		eb = _new_booking()
		with self.assertRaises(Exception):
			eb.validate_review_requirement()
		mock_frappe.throw.assert_called_once()

	def test_review_not_required_allows(self, mock_frappe, _):
		settings = SimpleNamespace(require_review=False)
		mock_frappe.get_cached_doc.return_value = settings

		eb = _new_booking()
		eb.validate_review_requirement()
		mock_frappe.throw.assert_not_called()

