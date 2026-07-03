"""Unit tests for EventBooking controller methods.

These tests mock frappe so they can run without a live Frappe site.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from event_bookings.event_bookings.doctype.event_booking.event_booking import EventBooking

_MODULE = "event_bookings.event_bookings.doctype.event_booking.event_booking"


def _new_booking(**overrides):
	"""Create a bare EventBooking instance without calling __init__."""
	eb = object.__new__(EventBooking)
	eb.staff_requirements = []
	eb.total_estimated = 0
	eb.total_actual = 0
	eb.quotation = None
	eb.sales_order = None
	eb.sales_invoice = None
	eb.material_request = None
	eb.booking_status = "New"
	eb.party_type = "Customer"
	eb.party_name = "Test Customer"
	eb.event_planner = None
	eb.event_name = "Test Event"
	eb.event_date = "2026-08-01"
	eb.event_time = "18:00:00"
	eb.event_location = "Venue"
	eb.name = "EVT-001"
	eb.company = None
	eb.cost_center = None
	eb.flags = SimpleNamespace(ignore_permissions=False)
	for k, v in overrides.items():
		setattr(eb, k, v)
	return eb


# ── calculate_totals ────────────────────────────────────────────────
# calculate_totals aggregates child-item amounts via the module-level
# _sql_items_total helper, so we patch that rather than the DB.


@patch(f"{_MODULE}._sql_items_total")
class TestCalculateTotals(unittest.TestCase):
	def test_no_linked_docs(self, mock_total):
		mock_total.return_value = 0.0
		eb = _new_booking()
		eb.calculate_totals()
		self.assertEqual(eb.total_estimated, 0.0)
		self.assertEqual(eb.total_actual, 0.0)

	def test_from_quotation(self, mock_total):
		mock_total.side_effect = lambda dt, name: 2500.0 if dt == "Quotation" else 0.0
		eb = _new_booking(quotation="QTN-001")
		eb.calculate_totals()
		self.assertEqual(eb.total_estimated, 2500.0)
		self.assertEqual(eb.total_actual, 0.0)

	def test_from_sales_order(self, mock_total):
		mock_total.side_effect = lambda dt, name: {"Quotation": 2500.0, "Sales Order": 3000.0}.get(dt, 0.0)
		eb = _new_booking(quotation="QTN-001", sales_order="SO-001")
		eb.calculate_totals()
		self.assertEqual(eb.total_estimated, 2500.0)
		self.assertEqual(eb.total_actual, 3000.0)

	def test_from_sales_invoice_when_no_so(self, mock_total):
		mock_total.side_effect = lambda dt, name: 4500.0 if dt == "Sales Invoice" else 0.0
		eb = _new_booking(sales_invoice="SI-001")
		eb.calculate_totals()
		self.assertEqual(eb.total_estimated, 0.0)
		self.assertEqual(eb.total_actual, 4500.0)


# ── validate_dates ──────────────────────────────────────────────────
# Rule: an EXISTING booking may not be moved to a past event_date; a NEW
# booking with a past date is allowed (e.g. backdated record entry).

_PAST = "2020-01-01"
_FUTURE = "2099-08-01"


@patch(f"{_MODULE}.today", return_value="2026-07-10")
@patch(f"{_MODULE}.frappe")
class TestValidateDates(unittest.TestCase):
	def test_past_date_existing_booking_throws(self, mock_frappe, _today):
		eb = _new_booking(event_date=_PAST)
		eb.is_new = lambda: False
		eb.validate_dates()
		mock_frappe.throw.assert_called_once()

	def test_past_date_new_booking_no_throw(self, mock_frappe, _today):
		eb = _new_booking(event_date=_PAST)
		eb.is_new = lambda: True
		eb.validate_dates()
		mock_frappe.throw.assert_not_called()

	def test_future_date_no_throw(self, mock_frappe, _today):
		eb = _new_booking(event_date=_FUTURE)
		eb.is_new = lambda: False
		eb.validate_dates()
		mock_frappe.throw.assert_not_called()

	def test_none_date_no_throw(self, mock_frappe, _today):
		eb = _new_booking(event_date=None)
		eb.is_new = lambda: True
		eb.validate_dates()
		mock_frappe.throw.assert_not_called()


if __name__ == "__main__":
	unittest.main()
