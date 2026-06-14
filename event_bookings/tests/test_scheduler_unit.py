import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from event_bookings.utils.scheduler import (
	daily,
	send_pre_event_reminders,
	send_unstaffed_alerts,
	sync_invoice_payment_status,
)


@patch("event_bookings.utils.scheduler.frappe")
class TestSyncInvoicePaymentStatus(unittest.TestCase):
	def test_transitions_to_paid_when_invoice_paid(self, mock_frappe):
		mock_frappe.get_all.return_value = [
			SimpleNamespace(name="EVT-001", sales_invoice="SINV-001"),
		]
		mock_frappe.db.get_value.return_value = "Paid"

		sync_invoice_payment_status()

		mock_frappe.db.set_value.assert_called_once_with("Event Booking", "EVT-001", "booking_status", "Paid")

	def test_does_not_transition_when_invoice_unpaid(self, mock_frappe):
		mock_frappe.get_all.return_value = [
			SimpleNamespace(name="EVT-002", sales_invoice="SINV-002"),
		]
		mock_frappe.db.get_value.return_value = "Unpaid"

		sync_invoice_payment_status()

		mock_frappe.get_doc.assert_not_called()

	def test_handles_no_invoiced_events(self, mock_frappe):
		mock_frappe.get_all.return_value = []
		sync_invoice_payment_status()
		mock_frappe.get_doc.assert_not_called()

	def test_handles_multiple_events(self, mock_frappe):
		mock_frappe.get_all.return_value = [
			SimpleNamespace(name="EVT-A", sales_invoice="SINV-A"),
			SimpleNamespace(name="EVT-B", sales_invoice="SINV-B"),
		]

		def get_value_side_effect(doctype, name, field):
			return "Paid" if name == "SINV-A" else "Unpaid"

		mock_frappe.db.get_value.side_effect = get_value_side_effect

		sync_invoice_payment_status()

		mock_frappe.get_doc.assert_not_called()
		mock_frappe.db.set_value.assert_called_once_with("Event Booking", "EVT-A", "booking_status", "Paid")


@patch("event_bookings.utils.scheduler.frappe")
@patch("event_bookings.utils.scheduler.add_days")
@patch("event_bookings.utils.scheduler.today", return_value="2026-07-10")
class TestSendPreEventReminders(unittest.TestCase):
	def test_queries_events_at_target_date(self, _today, mock_add_days, mock_frappe):
		mock_add_days.return_value = "2026-07-13"
		mock_frappe.get_all.return_value = []

		send_pre_event_reminders(days=3)

		mock_add_days.assert_called_once_with("2026-07-10", 3)
		mock_frappe.get_all.assert_called_once()
		call_kwargs = mock_frappe.get_all.call_args
		self.assertEqual(call_kwargs[1]["filters"]["event_date"], "2026-07-13")

	def test_custom_days_parameter(self, _today, mock_add_days, mock_frappe):
		mock_add_days.return_value = "2026-07-11"
		mock_frappe.get_all.return_value = []

		send_pre_event_reminders(days=1)

		mock_add_days.assert_called_once_with("2026-07-10", 1)


@patch("event_bookings.utils.scheduler.frappe")
class TestSendUnstaffedAlerts(unittest.TestCase):
	def test_iterates_staff_requirements(self, mock_frappe):
		req = SimpleNamespace(qty_assigned=1, qty_required=3)
		doc = MagicMock()
		doc.staff_requirements = [req]

		mock_frappe.get_all.return_value = [SimpleNamespace(name="EVT-001")]
		mock_frappe.get_doc.return_value = doc

		send_unstaffed_alerts()

		mock_frappe.get_doc.assert_called_once_with("Event Booking", "EVT-001")

	def test_skips_fully_staffed(self, mock_frappe):
		req = SimpleNamespace(qty_assigned=3, qty_required=3)
		doc = MagicMock()
		doc.staff_requirements = [req]

		mock_frappe.get_all.return_value = [SimpleNamespace(name="EVT-001")]
		mock_frappe.get_doc.return_value = doc

		# Should complete without error even when fully staffed
		send_unstaffed_alerts()

	def test_handles_no_events(self, mock_frappe):
		mock_frappe.get_all.return_value = []
		send_unstaffed_alerts()
		mock_frappe.get_doc.assert_not_called()


@patch("event_bookings.utils.scheduler.send_unstaffed_alerts")
@patch("event_bookings.utils.scheduler.send_pre_event_reminders")
@patch("event_bookings.utils.scheduler.sync_invoice_payment_status")
class TestDaily(unittest.TestCase):
	def test_calls_all_subtasks(self, mock_sync, mock_remind, mock_alert):
		daily()
		mock_sync.assert_called_once()
		mock_remind.assert_called_once_with(days=3)
		mock_alert.assert_called_once()
