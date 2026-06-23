"""Tests for Event Booking cancellation/reversal and scheduled reminders."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from event_bookings.utils.scheduler import send_pre_event_reminders, send_unstaffed_alerts


class TestCancellationAndReminders(unittest.TestCase):

	@patch("event_bookings.utils.scheduler.frappe")
	@patch("event_bookings.utils.scheduler.today")
	@patch("event_bookings.utils.scheduler.add_days")
	def test_pre_event_reminders_send_emails(self, mock_add_days, mock_today, mock_frappe):
		mock_today.return_value = "2026-08-01"
		mock_add_days.return_value = "2026-08-04"
		mock_frappe.get_all.side_effect = [
			[{"name": "EVT-001", "event_name": "Launch Party", "event_date": "2026-08-04"}],
			[{"email": "manager@example.com"}],
		]
		mock_frappe.sendmail.return_value = True

		send_pre_event_reminders(days=3)

		mock_frappe.sendmail.assert_called_once()
		args = mock_frappe.sendmail.call_args.kwargs
		self.assertIn("Reminder", args["subject"])
		self.assertEqual(args["reference_name"], "EVT-001")

	@patch("event_bookings.utils.scheduler.frappe")
	def test_unstaffed_alerts_only_when_understaffed(self, mock_frappe):
		mock_doc = MagicMock()
		mock_doc.event_name = "Gala"
		mock_doc.name = "EVT-002"
		mock_doc.staff_requirements = [
			MagicMock(designation="Waiter", qty_required=5, qty_assigned=2),
			MagicMock(designation="Bartender", qty_required=2, qty_assigned=2),
		]
		mock_frappe.get_doc.return_value = mock_doc
		mock_frappe.get_all.side_effect = [
			[{"name": "EVT-002"}],
			[{"email": "manager@example.com"}],
		]
		mock_frappe.sendmail.return_value = True

		send_unstaffed_alerts()

		mock_frappe.sendmail.assert_called_once()
		args = mock_frappe.sendmail.call_args.kwargs
		self.assertIn("Under-staffed", args["subject"])
		self.assertIn("Waiter: 2/5", args["message"])
		self.assertNotIn("Bartender", args["message"])
