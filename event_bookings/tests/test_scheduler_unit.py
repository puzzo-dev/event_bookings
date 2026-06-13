"""Unit tests for scheduler module."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


@patch("event_bookings.utils.scheduler.send_event_reminder")
@patch("event_bookings.utils.scheduler.frappe")
@patch("event_bookings.utils.scheduler.add_days")
@patch("event_bookings.utils.scheduler.today")
class TestSendPreEventReminders(unittest.TestCase):
	def test_sends_reminders_for_matching_events(self, mock_today, mock_add, mock_frappe, mock_send):
		from event_bookings.utils.scheduler import send_pre_event_reminders

		mock_today.return_value = "2026-07-10"
		mock_add.return_value = "2026-07-13"

		ev = SimpleNamespace(name="EVT-001", event_name="Gala", event_date="2026-07-13")
		mock_frappe.get_all.return_value = [ev]

		mock_doc = MagicMock()
		mock_frappe.get_doc.return_value = mock_doc

		send_pre_event_reminders(days=3)

		mock_frappe.get_doc.assert_called_once_with("Event Booking", "EVT-001")
		mock_send.assert_called_once_with(mock_doc, 3)

	def test_no_events_no_reminders(self, mock_today, mock_add, mock_frappe, mock_send):
		from event_bookings.utils.scheduler import send_pre_event_reminders

		mock_today.return_value = "2026-07-10"
		mock_add.return_value = "2026-07-13"
		mock_frappe.get_all.return_value = []

		send_pre_event_reminders(days=3)
		mock_send.assert_not_called()


@patch("event_bookings.utils.scheduler.send_unstaffed_alert")
@patch("event_bookings.utils.scheduler.frappe")
class TestSendUnstaffedAlerts(unittest.TestCase):
	def test_alerts_for_understaffed_event(self, mock_frappe, mock_alert):
		from event_bookings.utils.scheduler import send_unstaffed_alerts

		mock_frappe.get_all.return_value = [SimpleNamespace(name="EVT-001")]

		req = SimpleNamespace(designation="Waiter", qty_required=3, qty_assigned=1)
		mock_doc = MagicMock()
		mock_doc.staff_requirements = [req]
		mock_frappe.get_doc.return_value = mock_doc

		send_unstaffed_alerts()

		mock_alert.assert_called_once()
		call_args = mock_alert.call_args
		self.assertEqual(call_args[0][0], mock_doc)
		self.assertEqual(call_args[0][1], [{"designation": "Waiter", "gap": 2}])

	def test_no_alert_when_fully_staffed(self, mock_frappe, mock_alert):
		from event_bookings.utils.scheduler import send_unstaffed_alerts

		mock_frappe.get_all.return_value = [SimpleNamespace(name="EVT-001")]

		req = SimpleNamespace(designation="Chef", qty_required=2, qty_assigned=2)
		mock_doc = MagicMock()
		mock_doc.staff_requirements = [req]
		mock_frappe.get_doc.return_value = mock_doc

		send_unstaffed_alerts()
		mock_alert.assert_not_called()


@patch("event_bookings.utils.scheduler.frappe")
class TestSyncInvoicePaymentStatus(unittest.TestCase):
	def test_transitions_to_paid(self, mock_frappe):
		from event_bookings.utils.scheduler import sync_invoice_payment_status

		mock_frappe.get_all.return_value = [SimpleNamespace(name="EVT-001", sales_invoice="SI-001")]
		mock_frappe.db.get_value.return_value = "Paid"

		mock_doc = MagicMock()
		mock_frappe.get_doc.return_value = mock_doc

		sync_invoice_payment_status()

		mock_frappe.utils.apply_workflow.assert_called_once_with(mock_doc, "Mark Paid")

	def test_skips_unpaid_invoice(self, mock_frappe):
		from event_bookings.utils.scheduler import sync_invoice_payment_status

		mock_frappe.get_all.return_value = [SimpleNamespace(name="EVT-001", sales_invoice="SI-001")]
		mock_frappe.db.get_value.return_value = "Unpaid"

		sync_invoice_payment_status()
		mock_frappe.get_doc.assert_not_called()


@patch("event_bookings.utils.scheduler.send_unstaffed_alerts")
@patch("event_bookings.utils.scheduler.send_pre_event_reminders")
@patch("event_bookings.utils.scheduler.sync_invoice_payment_status")
class TestDaily(unittest.TestCase):
	def test_calls_all_tasks(self, mock_sync, mock_remind, mock_alert):
		from event_bookings.utils.scheduler import daily

		daily()

		mock_sync.assert_called_once()
		self.assertEqual(mock_remind.call_count, 2)
		mock_alert.assert_called_once()
