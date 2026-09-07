"""Unit tests for the Booking Review submit_review API.

These tests mock frappe so they can run without a live Frappe site.
"""

import unittest
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
	def setUp(self):
		# Default: frappe.throw raises so assertRaises works in throw-path tests.
		# Individual tests override side_effect when they need throw to NOT raise.
		pass

	def _configure_throw(self, mock_frappe):
		"""Make mocked frappe.throw actually raise so assertRaises works."""
		mock_frappe.throw.side_effect = Exception
		mock_frappe.PermissionError = Exception

	def test_missing_event_booking_throws(self, mock_frappe, _mock_auth):
		self._configure_throw(mock_frappe)
		with self.assertRaises(Exception):
			submit_review(None, rating=5, review_text="Great!")
		mock_frappe.throw.assert_called()

	def test_nonexistent_event_booking_throws(self, mock_frappe, _mock_auth):
		self._configure_throw(mock_frappe)
		mock_frappe.db.exists.return_value = False
		with self.assertRaises(Exception):
			submit_review("EVT-999", rating=5)
		mock_frappe.throw.assert_called()

	def test_wrong_status_throws(self, mock_frappe, _mock_auth):
		self._configure_throw(mock_frappe)
		mock_frappe.db.exists.return_value = True
		mock_frappe.db.get_value.return_value = "New"
		with self.assertRaises(Exception):
			submit_review("EVT-001", rating=5)
		mock_frappe.throw.assert_called()

	def test_no_customer_throws(self, mock_frappe, _mock_auth):
		self._configure_throw(mock_frappe)
		mock_frappe.db.exists.return_value = True
		mock_frappe.db.get_value.side_effect = ["Executed", None]
		with self.assertRaises(Exception):
			submit_review("EVT-001", rating=5)
		mock_frappe.throw.assert_called()

	@patch(
		"event_bookings.event_bookings.doctype.booking_review.booking_review._get_customer_contact_info",
		return_value=(None, None),
	)
	def test_no_email_throws(self, mock_contact, mock_frappe, _mock_auth):
		self._configure_throw(mock_frappe)
		mock_frappe.db.exists.return_value = True
		mock_frappe.db.get_value.side_effect = ["Executed", "Acme Corp"]
		with self.assertRaises(Exception):
			submit_review("EVT-001", rating=5)
		mock_frappe.throw.assert_called()

	@patch(
		"event_bookings.event_bookings.doctype.booking_review.booking_review._get_customer_contact_info",
		return_value=("Acme Corp", "acme@example.com"),
	)
	@patch(
		"event_bookings.event_bookings.doctype.booking_review.booking_review.validate_email_address",
		return_value=True,
	)
	@patch(
		"event_bookings.event_bookings.doctype.booking_review.booking_review.sanitize_html",
		return_value="Great!",
	)
	def test_rate_limit_blocks(self, _mock_sanitize, _mock_email, _mock_contact, mock_frappe, _mock_auth):
		self._configure_throw(mock_frappe)
		mock_frappe.db.exists.return_value = True
		mock_frappe.db.get_value.side_effect = ["Executed", "Acme Corp"]
		mock_frappe.cache.incr.return_value = 4  # exceeds _MAX_REVIEWS_PER_WINDOW (3)
		with self.assertRaises(Exception):
			submit_review("EVT-001", rating=5)
		mock_frappe.throw.assert_called()

	@patch(
		"event_bookings.event_bookings.doctype.booking_review.booking_review._get_customer_contact_info",
		return_value=("Acme Corp", "acme@example.com"),
	)
	@patch(
		"event_bookings.event_bookings.doctype.booking_review.booking_review.validate_email_address",
		return_value=True,
	)
	@patch(
		"event_bookings.event_bookings.doctype.booking_review.booking_review.sanitize_html",
		return_value="Great!",
	)
	def test_duplicate_within_24h_throws(self, _mock_sanitize, _mock_email, _mock_contact, mock_frappe, _mock_auth):
		self._configure_throw(mock_frappe)
		mock_frappe.db.exists.return_value = True
		mock_frappe.db.get_value.side_effect = [
			"Executed", "Acme Corp",  # status, customer
			"2026-07-15 10:00:00",    # last_review creation
		]
		mock_frappe.cache.incr.return_value = 1  # within limit
		mock_frappe.utils.time_diff_in_hours.return_value = 12
		with self.assertRaises(Exception):
			submit_review("EVT-001", rating=5)
		mock_frappe.throw.assert_called()

	@patch(
		"event_bookings.event_bookings.doctype.booking_review.booking_review._get_customer_contact_info",
		return_value=("Acme Corp", "acme@example.com"),
	)
	@patch(
		"event_bookings.event_bookings.doctype.booking_review.booking_review.validate_email_address",
		return_value=True,
	)
	@patch(
		"event_bookings.event_bookings.doctype.booking_review.booking_review.sanitize_html",
		return_value="Excellent event!",
	)
	def test_successful_submission(self, _mock_sanitize, _mock_email, _mock_contact, mock_frappe, _mock_auth):
		# Do NOT configure throw to raise — this test expects success.
		mock_frappe.db.exists.return_value = True
		mock_frappe.db.get_value.side_effect = [
			"Executed", "Acme Corp",  # status, customer
			None,                     # last_review creation (no duplicate)
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

	@patch(
		"event_bookings.event_bookings.doctype.booking_review.booking_review._get_customer_contact_info",
		return_value=("Acme Corp", "acme@example.com"),
	)
	@patch(
		"event_bookings.event_bookings.doctype.booking_review.booking_review.validate_email_address",
		return_value=True,
	)
	@patch(
		"event_bookings.event_bookings.doctype.booking_review.booking_review.sanitize_html",
		return_value="Great!",
	)
	def test_rate_limit_key_includes_event(self, _mock_sanitize, _mock_email, _mock_contact, mock_frappe, _mock_auth):
		# Do NOT configure throw to raise — this test expects success.
		mock_frappe.db.exists.return_value = True
		mock_frappe.db.get_value.side_effect = [
			"Executed", "Acme Corp",  # status, customer
			None,                     # last_review creation
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
		# _get_primary_contact_for_customer uses frappe.db.sql, not get_value
		mock_frappe.db.sql.return_value = [["CONT-001"]]
		# _get_customer_contact_info calls get_value with as_dict=True for Contact
		mock_frappe.db.get_value.return_value = {
			"first_name": "John",
			"email_id": "john@acme.com",
		}
		name, email = _get_customer_contact_info("Acme Corp")
		self.assertEqual(name, "John")
		self.assertEqual(email, "john@acme.com")

	def test_fallback_to_customer(self, mock_frappe):
		# No primary contact found
		mock_frappe.db.sql.return_value = []
		# Fallback: Customer email_id, then Customer customer_name
		mock_frappe.db.get_value.side_effect = [
			"acme@example.com",  # Customer email_id
			"Acme Corp",         # Customer customer_name
		]
		name, email = _get_customer_contact_info("Acme Corp")
		self.assertEqual(name, "Acme Corp")
		self.assertEqual(email, "acme@example.com")
