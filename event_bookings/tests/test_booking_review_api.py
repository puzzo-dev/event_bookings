"""Unit tests for the Booking Review submit_review API.

These tests mock frappe so they can run without a live Frappe site.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from event_bookings.event_bookings.doctype.booking_review.booking_review import (
	submit_review,
	_get_customer_contact_info,
)


@patch(
	"event_bookings.event_bookings.doctype.booking_review.booking_review._get_submitted_via",
	return_value="Direct",
)
@patch("event_bookings.event_bookings.doctype.booking_review.booking_review.frappe")
class TestSubmitReview(unittest.TestCase):
	def test_missing_event_booking_throws(self, mock_frappe, _mock_auth):
		with self.assertRaises(Exception):
			submit_review(None, rating=5, review_text="Great!")
		mock_frappe.throw.assert_called()

	def test_nonexistent_event_booking_throws(self, mock_frappe, _mock_auth):
		mock_frappe.db.exists.return_value = False
		with self.assertRaises(Exception):
			submit_review("EVT-999", rating=5)
		mock_frappe.throw.assert_called()

	def test_wrong_status_throws(self, mock_frappe, _mock_auth):
		mock_frappe.db.exists.return_value = True
		mock_frappe.db.get_value.return_value = "New"
		with self.assertRaises(Exception):
			submit_review("EVT-001", rating=5)
		mock_frappe.throw.assert_called()

	def test_no_customer_throws(self, mock_frappe, _mock_auth):
		mock_frappe.db.exists.return_value = True
		mock_frappe.db.get_value.side_effect = ["Executed", None]
		with self.assertRaises(Exception):
			submit_review("EVT-001", rating=5)
		mock_frappe.throw.assert_called()

	def test_no_email_throws(self, mock_frappe, _mock_auth):
		mock_frappe.db.exists.return_value = True
		mock_frappe.db.get_value.side_effect = [
			"Executed", "Acme Corp",  # status, customer
			None, None, None,          # _get_customer_contact_info fallbacks
			"Acme Corp",               # customer_name fallback
		]
		with self.assertRaises(Exception):
			submit_review("EVT-001", rating=5)
		mock_frappe.throw.assert_called()

	def test_rate_limit_blocks(self, mock_frappe, _mock_auth):
		mock_frappe.db.exists.return_value = True
		mock_frappe.db.get_value.side_effect = [
			"Executed", "Acme Corp", "acme@example.com",
			None, None, None,
			"Acme Corp",
		]
		mock_frappe.cache.incr.return_value = 4  # exceeds _MAX_REVIEWS_PER_WINDOW (3)
		with self.assertRaises(Exception):
			submit_review("EVT-001", rating=5)
		mock_frappe.throw.assert_called()

	def test_duplicate_within_24h_throws(self, mock_frappe, _mock_auth):
		mock_frappe.db.exists.return_value = True
		mock_frappe.db.get_value.side_effect = [
			"Executed", "Acme Corp", "acme@example.com",
			None, None, None,
			"Acme Corp", "acme@example.com", "2026-07-15 10:00:00",
		]
		mock_frappe.cache.incr.return_value = 1  # within limit
		mock_frappe.utils.time_diff_in_hours.return_value = 12
		with self.assertRaises(Exception):
			submit_review("EVT-001", rating=5)
		mock_frappe.throw.assert_called()

	def test_successful_submission(self, mock_frappe, _mock_auth):
		mock_frappe.db.exists.return_value = True
		mock_frappe.db.get_value.side_effect = [
			"Executed", "Acme Corp", "acme@example.com",
			None, None, None,
			"Acme Corp", None, None,
		]
		mock_frappe.cache.incr.return_value = 1  # within limit
		mock_frappe.utils.time_diff_in_hours.return_value = 48

		mock_review = MagicMock()
		mock_review.name = "BR-001"
		mock_frappe.get_doc.return_value = mock_review

		result = submit_review("EVT-001", rating=5, review_text="Excellent event!")

		self.assertEqual(result["message"], "Review submitted successfully.")
		self.assertEqual(result["name"], "BR-001")
		mock_review.insert.assert_called_once()

	def test_rate_limit_key_includes_event(self, mock_frappe, _mock_auth):
		"""Ensure rate limit is scoped per customer+event, not just customer."""
		mock_frappe.db.exists.return_value = True
		mock_frappe.db.get_value.side_effect = [
			"Executed", "Acme Corp", "acme@example.com",
			None, None, None,
			"Acme Corp", None, None,
		]
		mock_frappe.cache.incr.return_value = 1  # within limit
		mock_frappe.utils.time_diff_in_hours.return_value = 48

		mock_review = MagicMock()
		mock_review.name = "BR-001"
		mock_frappe.get_doc.return_value = mock_review

		submit_review("EVT-001", rating=5, review_text="Great!")

		incr_call = mock_frappe.cache.incr.call_args
		self.assertIsNotNone(incr_call)
		key = incr_call[0][0]
		self.assertIn("EVT-001", key)


@patch("event_bookings.event_bookings.doctype.booking_review.booking_review.frappe")
class TestGetCustomerContactInfo(unittest.TestCase):
	def test_uses_primary_contact(self, mock_frappe):
		mock_frappe.db.get_value.side_effect = [
			"CONT-001",  # Dynamic Link parent
			"John",       # Contact first_name
			"john@acme.com",  # Contact email_id
		]
		name, email = _get_customer_contact_info("Acme Corp")
		self.assertEqual(name, "John")
		self.assertEqual(email, "john@acme.com")

	def test_fallback_to_customer(self, mock_frappe):
		mock_frappe.db.get_value.side_effect = [
			None, None, None,  # No contact
			"acme@example.com",  # Customer email_id
			"Acme Corp",         # Customer name
		]
		name, email = _get_customer_contact_info("Acme Corp")
		self.assertEqual(name, "Acme Corp")
		self.assertEqual(email, "acme@example.com")
