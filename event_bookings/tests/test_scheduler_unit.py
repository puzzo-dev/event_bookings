"""Unit tests for scheduler functions.

Only ``send_unstaffed_alerts`` has custom logic that needs unit testing
with mocks. ``auto_execute_passed_events`` is covered by integration tests
in ``test_status_automation.py``.

The removed functions (``sync_invoice_payment_status``,
``send_pre_event_reminders``, ``notify_managers_upcoming_events``) were
redundant with Frappe's built-in Notification service and event-driven
hooks — their tests are removed accordingly.
"""

import unittest
from unittest.mock import patch

from event_bookings.utils.scheduler import send_unstaffed_alerts


@patch("event_bookings.utils.scheduler._get_manager_emails", return_value=["mgr@example.com"])
@patch("event_bookings.utils.scheduler._", side_effect=lambda x, *a: x.format(*a) if a else x)
@patch("event_bookings.utils.scheduler.today", return_value="2026-07-10")
@patch("event_bookings.utils.scheduler.frappe")
class TestSendUnstaffedAlerts(unittest.TestCase):
	def test_sends_alert_for_shortfall(self, mock_frappe, _mock_today, _mock_i18n, _mock_mgr):
		mock_frappe.db.sql.return_value = [
			{
				"name": "EVT-001",
				"event_name": "Test Event",
				"event_date": "2026-07-15",
				"designation": "Waiter",
				"qty_required": 3,
				"qty_assigned": 1,
			}
		]

		send_unstaffed_alerts()

		mock_frappe.db.sql.assert_called_once()
		mock_frappe.sendmail.assert_called_once()
		call_kwargs = mock_frappe.sendmail.call_args[1]
		self.assertEqual(call_kwargs["recipients"], ["mgr@example.com"])

	def test_skips_when_no_managers(self, mock_frappe, _mock_today, _mock_i18n, _mock_mgr):
		_mock_mgr.return_value = []
		send_unstaffed_alerts()
		mock_frappe.sendmail.assert_not_called()

	def test_handles_no_shortfalls(self, mock_frappe, _mock_today, _mock_i18n, _mock_mgr):
		mock_frappe.db.sql.return_value = []
		send_unstaffed_alerts()
		mock_frappe.sendmail.assert_not_called()
