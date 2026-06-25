import unittest
from unittest.mock import MagicMock, call, patch

from event_bookings.utils.scheduler import (
	daily,
	send_unstaffed_alerts,
	sync_invoice_payment_status,
)


@patch("event_bookings.utils.scheduler.frappe")
class TestSyncInvoicePaymentStatus(unittest.TestCase):
	def test_executes_update_join(self, mock_frappe):
		"""sync_invoice_payment_status uses a single UPDATE JOIN — no N+1 loop."""
		sync_invoice_payment_status()
		mock_frappe.db.sql.assert_called_once()
		sql = mock_frappe.db.sql.call_args[0][0]
		self.assertIn("tabEvent Booking", sql)
		self.assertIn("tabSales Invoice", sql)
		self.assertIn("Paid", sql)

	def test_commits_after_update(self, mock_frappe):
		sync_invoice_payment_status()
		mock_frappe.db.commit.assert_called_once()

	def test_uses_session_user_not_hardcoded(self, mock_frappe):
		"""modified_by must use frappe.session.user, not the literal string 'Administrator'."""
		sync_invoice_payment_status()
		sql = mock_frappe.db.sql.call_args[0][0]
		self.assertNotIn("'Administrator'", sql)
		params = mock_frappe.db.sql.call_args[0][1]
		self.assertIn(mock_frappe.session.user, params)


@patch("event_bookings.utils.scheduler.frappe")
class TestSendUnstaffedAlerts(unittest.TestCase):
	def test_delegates_to_notification(self, mock_frappe):
		"""send_unstaffed_alerts must call notification.send(doc), not frappe.sendmail."""
		mock_frappe.db.sql.return_value = [{"name": "EVT-001"}]
		mock_doc = MagicMock()
		mock_notification = MagicMock()
		mock_frappe.DoesNotExistError = Exception

		def fake_get_doc(doctype, name=None):
			if doctype == "Event Booking":
				return mock_doc
			if doctype == "Notification":
				return mock_notification
			return MagicMock()

		mock_frappe.get_doc.side_effect = fake_get_doc
		send_unstaffed_alerts()
		mock_notification.send.assert_called_once_with(mock_doc)

	def test_skips_when_no_understaffed_events(self, mock_frappe):
		mock_frappe.db.sql.return_value = []
		send_unstaffed_alerts()
		mock_frappe.get_doc.assert_not_called()

	def test_logs_error_when_notification_missing(self, mock_frappe):
		mock_frappe.db.sql.return_value = [{"name": "EVT-002"}]
		mock_frappe.DoesNotExistError = KeyError
		mock_frappe.get_doc.side_effect = KeyError("Notification not found")
		send_unstaffed_alerts()
		mock_frappe.log_error.assert_called_once()


@patch("event_bookings.utils.scheduler.send_unstaffed_alerts")
@patch("event_bookings.utils.scheduler.sync_invoice_payment_status")
class TestDaily(unittest.TestCase):
	def test_calls_all_subtasks(self, mock_sync, mock_alert):
		daily()
		mock_sync.assert_called_once()
		mock_alert.assert_called_once()

	def test_isolates_task_failures(self, mock_sync, mock_alert):
		"""A failure in one task must not prevent the others from running."""
		mock_sync.side_effect = Exception("DB down")
		with patch("event_bookings.utils.scheduler.frappe") as mock_frappe:
			daily()
		mock_alert.assert_called_once()
