"""Tests for Event Booking cancellation/reversal and scheduled alerts."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from event_bookings.utils.scheduler import send_unstaffed_alerts


_SHORTFALL_ROW = {
    "name": "EVT-002",
    "event_name": "Test Event",
    "event_date": "2026-07-20",
    "designation": "DJ",
    "qty_required": 2,
    "qty_assigned": 0,
}


class TestUnstaffedAlerts(unittest.TestCase):

    @patch("event_bookings.utils.scheduler.frappe")
    def test_alerts_send_email_digest(self, mock_frappe):
        """send_unstaffed_alerts sends a single digest via frappe.sendmail."""
        mock_frappe.get_all.side_effect = [
            ["manager@example.com"],            # Has Role → pluck="parent"
            [{"email": "manager@example.com"}], # User email rows
        ]
        mock_frappe.db.sql.return_value = [_SHORTFALL_ROW]
        mock_frappe.utils.formatdate.return_value = "20-07-2026"

        send_unstaffed_alerts()

        mock_frappe.sendmail.assert_called_once()
        recipients = mock_frappe.sendmail.call_args[1]["recipients"]
        self.assertIn("manager@example.com", recipients)

    @patch("event_bookings.utils.scheduler.frappe")
    def test_no_alert_when_fully_staffed(self, mock_frappe):
        """send_unstaffed_alerts does nothing when no events are understaffed."""
        mock_frappe.get_all.side_effect = [
            ["manager@example.com"],
            [{"email": "manager@example.com"}],
        ]
        mock_frappe.db.sql.return_value = []

        send_unstaffed_alerts()

        mock_frappe.sendmail.assert_not_called()

    @patch("event_bookings.utils.scheduler.frappe")
    def test_sendmail_error_is_logged(self, mock_frappe):
        """send_unstaffed_alerts logs an error if sendmail raises."""
        mock_frappe.get_all.side_effect = [
            ["manager@example.com"],
            [{"email": "manager@example.com"}],
        ]
        mock_frappe.db.sql.return_value = [_SHORTFALL_ROW]
        mock_frappe.utils.formatdate.return_value = "20-07-2026"
        mock_frappe.DatabaseError = Exception
        mock_frappe.ValidationError = Exception
        mock_frappe.sendmail.side_effect = Exception("DB error")

        send_unstaffed_alerts()

        mock_frappe.log_error.assert_called()
