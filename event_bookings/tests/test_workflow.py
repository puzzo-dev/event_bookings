"""Unit tests for status transition validation (no Frappe Workflow required)."""

import unittest
from unittest.mock import MagicMock, patch


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestValidStatusTransitions(unittest.TestCase):
	def _make_booking(self, mock_frappe, old_status="New", new_status="Quoted"):
		from event_bookings.event_bookings.doctype.event_booking.event_booking import EventBooking

		eb = EventBooking.__new__(EventBooking)
		eb.doctype = "Event Booking"
		eb.name = "EVT-001"
		eb.booking_status = new_status
		eb.flags = MagicMock()
		mock_frappe.db.get_value.return_value = old_status
		eb.is_new = MagicMock(return_value=False)
		return eb

	def test_new_to_quoted_allowed(self, mock_frappe):
		eb = self._make_booking(mock_frappe, "New", "Quoted")
		eb._validate_status_transition()
		mock_frappe.throw.assert_not_called()

	def test_new_to_cancelled_allowed(self, mock_frappe):
		eb = self._make_booking(mock_frappe, "New", "Cancelled")
		eb._validate_status_transition()
		mock_frappe.throw.assert_not_called()

	def test_quoted_to_confirmed_allowed(self, mock_frappe):
		eb = self._make_booking(mock_frappe, "Quoted", "Confirmed")
		eb._validate_status_transition()
		mock_frappe.throw.assert_not_called()

	def test_quoted_to_negotiating_allowed(self, mock_frappe):
		eb = self._make_booking(mock_frappe, "Quoted", "Negotiating")
		eb._validate_status_transition()
		mock_frappe.throw.assert_not_called()

	def test_new_to_confirmed_blocked(self, mock_frappe):
		eb = self._make_booking(mock_frappe, "New", "Confirmed")
		eb._validate_status_transition()
		mock_frappe.throw.assert_called_once()

	def test_quoted_to_paid_blocked(self, mock_frappe):
		eb = self._make_booking(mock_frappe, "Quoted", "Paid")
		eb._validate_status_transition()
		mock_frappe.throw.assert_called_once()

	def test_cancelled_to_anything_blocked(self, mock_frappe):
		eb = self._make_booking(mock_frappe, "Cancelled", "New")
		eb._validate_status_transition()
		mock_frappe.throw.assert_called_once()

	def test_same_status_no_validation(self, mock_frappe):
		eb = self._make_booking(mock_frappe, "New", "New")
		eb._validate_status_transition()
		mock_frappe.throw.assert_not_called()

	def test_skips_on_new_doc(self, mock_frappe):
		eb = self._make_booking(mock_frappe, "New", "Paid")
		eb.is_new.return_value = True
		eb._validate_status_transition()
		mock_frappe.throw.assert_not_called()

	def test_full_happy_path(self, mock_frappe):
		"""Validate the complete lifecycle path is allowed."""
		from event_bookings.event_bookings.doctype.event_booking.event_booking import EventBooking

		path = [
			"New",
			"Quoted",
			"Confirmed",
			"In Preparation",
			"Executed",
			"Invoiced",
			"Paid",
		]
		for i in range(len(path) - 1):
			eb = self._make_booking(mock_frappe, path[i], path[i + 1])
			mock_frappe.throw.reset_mock()
			eb._validate_status_transition()
			mock_frappe.throw.assert_not_called(), (f"Transition {path[i]}→{path[i + 1]} should be allowed")
