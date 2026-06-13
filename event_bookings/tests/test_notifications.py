"""Unit tests for notifications module."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from event_bookings.utils.notifications import format_whatsapp_message


class TestFormatWhatsappMessage(unittest.TestCase):
	def _make_doc(self):
		return SimpleNamespace(
			event_name="Annual Gala",
			customer="Acme Corp",
			event_date="2026-07-15",
			event_location="Grand Ballroom",
		)

	@patch("event_bookings.utils.notifications.formatdate", side_effect=lambda d: d)
	def test_basic_substitution(self, _fmt):
		tpl = "Event: {event_name} for {customer} on {event_date} at {event_location}"
		result = format_whatsapp_message(tpl, self._make_doc())
		self.assertEqual(result, "Event: Annual Gala for Acme Corp on 2026-07-15 at Grand Ballroom")

	@patch("event_bookings.utils.notifications.formatdate", side_effect=lambda d: d)
	def test_partial_template(self, _fmt):
		result = format_whatsapp_message("Hi {customer}", self._make_doc())
		self.assertEqual(result, "Hi Acme Corp")

	@patch("event_bookings.utils.notifications.formatdate")
	def test_formatdate_called(self, mock_fmt):
		mock_fmt.return_value = "Jul 15, 2026"
		result = format_whatsapp_message("{event_date}", self._make_doc())
		self.assertEqual(result, "Jul 15, 2026")
		mock_fmt.assert_called_once_with("2026-07-15")

	@patch("event_bookings.utils.notifications.formatdate", side_effect=lambda d: d)
	def test_empty_fields(self, _fmt):
		doc = SimpleNamespace(event_name="", customer="", event_date="", event_location="")
		result = format_whatsapp_message("{event_name}/{customer}", doc)
		self.assertEqual(result, "/")

	@patch("event_bookings.utils.notifications.frappe")
	@patch("event_bookings.utils.notifications.formatdate", side_effect=lambda d: d)
	def test_missing_placeholder_raises(self, _fmt, mock_frappe):
		mock_frappe.throw.side_effect = Exception("ValidationError")
		with self.assertRaises(Exception):
			format_whatsapp_message("{nonexistent}", self._make_doc())
		mock_frappe.log_error.assert_called_once()
		mock_frappe.throw.assert_called_once()


@patch("event_bookings.utils.notifications.frappe")
@patch("event_bookings.utils.notifications.formatdate", side_effect=lambda d: d)
class TestSendEventReminder(unittest.TestCase):
	def test_sends_email_with_recipients(self, _fmt, mock_frappe):
		from event_bookings.utils.notifications import send_event_reminder

		settings = SimpleNamespace(notification_email="mgr@test.com", enable_whatsapp=False)
		mock_frappe.get_cached_doc.return_value = settings
		mock_frappe.db.get_value.return_value = None

		doc = SimpleNamespace(
			name="EVT-001",
			event_name="Gala",
			customer="Acme",
			event_date="2026-07-15",
			event_location="Hall",
			contact_person=None,
			event_planner=None,
		)
		send_event_reminder(doc, 3)
		mock_frappe.sendmail.assert_called_once()

	def test_skips_when_no_recipients(self, _fmt, mock_frappe):
		from event_bookings.utils.notifications import send_event_reminder

		settings = SimpleNamespace(notification_email=None, enable_whatsapp=False)
		mock_frappe.get_cached_doc.return_value = settings

		doc = SimpleNamespace(
			name="EVT-001",
			event_name="Gala",
			customer="Acme",
			event_date="2026-07-15",
			event_location="Hall",
			contact_person=None,
			event_planner=None,
		)
		send_event_reminder(doc, 3)
		mock_frappe.sendmail.assert_not_called()

	def test_logs_error_on_email_failure(self, _fmt, mock_frappe):
		from event_bookings.utils.notifications import send_event_reminder

		settings = SimpleNamespace(notification_email="mgr@test.com", enable_whatsapp=False)
		mock_frappe.get_cached_doc.return_value = settings
		mock_frappe.db.get_value.return_value = None
		mock_frappe.sendmail.side_effect = Exception("SMTP error")

		doc = SimpleNamespace(
			name="EVT-001",
			event_name="Gala",
			customer="Acme",
			event_date="2026-07-15",
			event_location="Hall",
			contact_person=None,
			event_planner=None,
		)
		send_event_reminder(doc, 3)
		mock_frappe.log_error.assert_called_once()


@patch("event_bookings.utils.notifications.frappe")
@patch("event_bookings.utils.notifications.formatdate", side_effect=lambda d: d)
class TestSendUnstaffedAlert(unittest.TestCase):
	def test_sends_alert_to_manager(self, _fmt, mock_frappe):
		from event_bookings.utils.notifications import send_unstaffed_alert

		settings = SimpleNamespace(notification_email="mgr@test.com")
		mock_frappe.get_cached_doc.return_value = settings

		doc = SimpleNamespace(
			name="EVT-001",
			event_name="Gala",
			event_date="2026-07-15",
			event_planner=None,
		)
		unstaffed = [{"designation": "Waiter", "gap": 2}]
		send_unstaffed_alert(doc, unstaffed)
		mock_frappe.sendmail.assert_called_once()
