"""Unit tests for the customer portal API."""

import unittest
from unittest.mock import MagicMock, patch

import frappe
from event_bookings.api.portal import (
	_get_customer_for_user,
	has_website_permission,
)


def _ensure_frappe_local():
	"""Ensure frappe.local.flags is accessible for whitelisted functions."""
	if not hasattr(frappe.local, "flags"):
		frappe.local.flags = frappe._dict(in_test=True)
	else:
		frappe.local.flags.in_test = True


@patch("event_bookings.api.portal.frappe")
class TestGetCustomerBookings(unittest.TestCase):
	def setUp(self):
		_ensure_frappe_local()

	def test_guest_throws(self, mock_frappe):
		mock_frappe.session.user = "Guest"
		mock_frappe.AuthenticationError = Exception
		mock_frappe.throw.side_effect = Exception("Not logged in")

		from event_bookings.api.portal import get_customer_bookings

		with self.assertRaises(Exception):
			get_customer_bookings()

	def test_returns_empty_when_no_customer(self, mock_frappe):
		mock_frappe.session.user = "user@test.com"
		mock_frappe.db.get_value.return_value = None

		from event_bookings.api.portal import get_customer_bookings

		result = get_customer_bookings()
		self.assertEqual(result, [])

	def test_returns_bookings_for_customer(self, mock_frappe):
		mock_frappe.session.user = "user@test.com"
		mock_frappe.db.get_value.return_value = "CONTACT-001"
		mock_frappe.get_all.side_effect = [
			[MagicMock(link_name="CUST-001")],
			[{"name": "EVT-001", "event_name": "Gala"}],
		]

		from event_bookings.api.portal import get_customer_bookings

		result = get_customer_bookings()
		self.assertEqual(len(result), 1)

	def test_pagination_params_passed(self, mock_frappe):
		mock_frappe.session.user = "user@test.com"
		mock_frappe.db.get_value.return_value = "CONTACT-001"
		mock_frappe.get_all.side_effect = [
			[MagicMock(link_name="CUST-001")],
			[],
		]

		from event_bookings.api.portal import get_customer_bookings

		get_customer_bookings(limit_start=10, limit_page_length=5)
		call_args = mock_frappe.get_all.call_args_list[1]
		self.assertEqual(call_args[1]["start"], 10)
		self.assertEqual(call_args[1]["limit_page_length"], 5)

	def test_pagination_capped_at_100(self, mock_frappe):
		mock_frappe.session.user = "user@test.com"
		mock_frappe.db.get_value.return_value = "CONTACT-001"
		mock_frappe.get_all.side_effect = [
			[MagicMock(link_name="CUST-001")],
			[],
		]

		from event_bookings.api.portal import get_customer_bookings

		get_customer_bookings(limit_start=0, limit_page_length=999)
		call_args = mock_frappe.get_all.call_args_list[1]
		self.assertEqual(call_args[1]["limit_page_length"], 100)


@patch("event_bookings.api.portal.frappe")
class TestApproveQuotation(unittest.TestCase):
	def setUp(self):
		_ensure_frappe_local()

	def test_guest_throws(self, mock_frappe):
		mock_frappe.session.user = "Guest"
		mock_frappe.AuthenticationError = Exception
		mock_frappe.throw.side_effect = Exception("Not logged in")

		from event_bookings.api.portal import approve_quotation

		with self.assertRaises(Exception):
			approve_quotation("EVT-001")

	def test_wrong_customer_throws(self, mock_frappe):
		mock_frappe.session.user = "user@test.com"
		mock_frappe.db.get_value.return_value = "CONTACT-001"
		mock_frappe.get_all.return_value = [MagicMock(link_name="CUST-OTHER")]
		mock_frappe.PermissionError = PermissionError
		mock_frappe.throw.side_effect = PermissionError("No permission")

		mock_doc = MagicMock()
		mock_doc.customer = "CUST-001"
		mock_frappe.get_doc.return_value = mock_doc

		from event_bookings.api.portal import approve_quotation

		with self.assertRaises(PermissionError):
			approve_quotation("EVT-001")

	def test_confirms_quoted_booking(self, mock_frappe):
		mock_frappe.session.user = "user@test.com"
		mock_frappe.db.get_value.return_value = "CONTACT-001"
		mock_frappe.get_all.return_value = [MagicMock(link_name="CUST-001")]

		mock_doc = MagicMock()
		mock_doc.customer = "CUST-001"
		mock_doc.booking_status = "Quoted"
		mock_frappe.get_doc.return_value = mock_doc

		from event_bookings.api.portal import approve_quotation

		result = approve_quotation("EVT-001")

		self.assertEqual(mock_doc.booking_status, "Confirmed")
		mock_doc.save.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(result["status"], "success")


@patch("event_bookings.api.portal.frappe")
class TestGetCustomerForUser(unittest.TestCase):
	def test_returns_none_when_no_contact(self, mock_frappe):
		mock_frappe.db.get_value.return_value = None
		result = _get_customer_for_user("user@test.com")
		self.assertIsNone(result)

	def test_returns_customer_from_contact(self, mock_frappe):
		mock_frappe.db.get_value.return_value = "CONTACT-001"
		mock_frappe.get_all.return_value = [MagicMock(link_name="CUST-001")]

		result = _get_customer_for_user("user@test.com")
		self.assertEqual(result, "CUST-001")


class TestHasWebsitePermission(unittest.TestCase):
	@patch("event_bookings.api.portal._get_customer_for_user")
	def test_denies_guest(self, mock_get_cust):
		doc = MagicMock()
		self.assertFalse(has_website_permission(doc, "read", "Guest"))

	@patch("event_bookings.api.portal._get_customer_for_user")
	def test_denies_wrong_customer(self, mock_get_cust):
		mock_get_cust.return_value = "CUST-OTHER"
		doc = MagicMock()
		doc.customer = "CUST-001"
		self.assertFalse(has_website_permission(doc, "read", "user@test.com"))

	@patch("event_bookings.api.portal._get_customer_for_user")
	def test_allows_correct_customer(self, mock_get_cust):
		mock_get_cust.return_value = "CUST-001"
		doc = MagicMock()
		doc.customer = "CUST-001"
		self.assertTrue(has_website_permission(doc, "read", "user@test.com"))
