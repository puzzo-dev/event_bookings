"""Tests for Event Booking cancellation/reversal and scheduled alerts."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from event_bookings.utils.scheduler import send_unstaffed_alerts


class TestUnstaffedAlerts(unittest.TestCase):

    @patch("event_bookings.utils.scheduler.frappe")
    def test_alerts_send_via_notification(self, mock_frappe):
        """send_unstaffed_alerts delegates email to the Notification DocType."""
        mock_frappe.db.sql.return_value = [{"name": "EVT-002"}]
        mock_doc = MagicMock()
        mock_doc.name = "EVT-002"
        mock_notification = MagicMock()

        def fake_get_doc(doctype, name=None):
            if doctype == "Event Booking":
                return mock_doc
            if doctype == "Notification":
                return mock_notification
            return MagicMock()

        mock_frappe.get_doc.side_effect = fake_get_doc
        mock_frappe.DoesNotExistError = Exception

        send_unstaffed_alerts()

        mock_notification.send.assert_called_once_with(mock_doc)

    @patch("event_bookings.utils.scheduler.frappe")
    def test_no_alert_when_fully_staffed(self, mock_frappe):
        """send_unstaffed_alerts does nothing when no events are understaffed."""
        mock_frappe.db.sql.return_value = []

        send_unstaffed_alerts()

        mock_frappe.get_doc.assert_not_called()

    @patch("event_bookings.utils.scheduler.frappe")
    def test_missing_notification_logs_error(self, mock_frappe):
        """send_unstaffed_alerts logs an error if the Notification record is missing."""
        mock_frappe.db.sql.return_value = [{"name": "EVT-003"}]
        mock_frappe.DoesNotExistError = KeyError

        mock_frappe.get_doc.side_effect = KeyError("Notification not found")

        send_unstaffed_alerts()

        mock_frappe.log_error.assert_called_once()
        title = mock_frappe.log_error.call_args.kwargs.get("title", "")
        self.assertIn("not found", title)
