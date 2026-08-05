import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from event_bookings.utils.scheduler import (
	daily,
	notify_managers_upcoming_events,
	send_unstaffed_alerts,
	sync_invoice_payment_status,
)


@patch("event_bookings.utils.scheduler.frappe")
class TestSyncInvoicePaymentStatus(unittest.TestCase):
	def _setup_batch(self, mock_frappe, eb_rows, si_status_rows):
		"""Configure get_all side_effect for two-call batch pattern."""
		call_count = [0]

		def get_all_side_effect(doctype, **kwargs):
			call_count[0] += 1
			if call_count[0] == 1:
				return eb_rows
			return si_status_rows

		mock_frappe.get_all.side_effect = get_all_side_effect
		# Make frappe._dict behave like real dict constructor
		mock_frappe._dict.side_effect = dict

	def test_transitions_to_paid_when_invoice_paid(self, mock_frappe):
		self._setup_batch(
			mock_frappe,
			eb_rows=[SimpleNamespace(name="EVT-001", sales_invoice="SINV-001")],
			si_status_rows=[["SINV-001", "Paid"]],
		)
		mock_frappe.db.get_value.return_value = SimpleNamespace(booking_status="Invoiced", docstatus=1)

		sync_invoice_payment_status()

		mock_frappe.db.set_value.assert_called_once_with("Event Booking", "EVT-001", "booking_status", "Paid")

	def test_does_not_transition_when_invoice_unpaid(self, mock_frappe):
		self._setup_batch(
			mock_frappe,
			eb_rows=[SimpleNamespace(name="EVT-002", sales_invoice="SINV-002")],
			si_status_rows=[["SINV-002", "Unpaid"]],
		)

		sync_invoice_payment_status()

		mock_frappe.db.set_value.assert_not_called()

	def test_handles_no_invoiced_events(self, mock_frappe):
		mock_frappe.get_all.return_value = []
		sync_invoice_payment_status()
		mock_frappe.db.set_value.assert_not_called()

	def test_handles_multiple_events(self, mock_frappe):
		self._setup_batch(
			mock_frappe,
			eb_rows=[
				SimpleNamespace(name="EVT-A", sales_invoice="SINV-A"),
				SimpleNamespace(name="EVT-B", sales_invoice="SINV-B"),
			],
			si_status_rows=[["SINV-A", "Paid"], ["SINV-B", "Unpaid"]],
		)
		# EVT-A: booking is Invoiced+submitted; EVT-B: invoice not Paid so skipped
		mock_frappe.db.get_value.return_value = SimpleNamespace(booking_status="Invoiced", docstatus=1)

		sync_invoice_payment_status()

		mock_frappe.db.set_value.assert_called_once_with("Event Booking", "EVT-A", "booking_status", "Paid")


@patch("event_bookings.utils.scheduler._get_manager_emails", return_value=["mgr@example.com"])
@patch("event_bookings.utils.scheduler._", side_effect=lambda x, *a: x.format(*a) if a else x)
@patch("event_bookings.utils.scheduler.today", return_value="2026-07-10")
@patch("event_bookings.utils.scheduler.frappe")
class TestSendUnstaffedAlerts(unittest.TestCase):
	def test_sends_alert_for_shortfall(self, mock_frappe, _mock_today, _mock_i18n, _mock_mgr):
		mock_frappe.db.sql.return_value = [
			SimpleNamespace(
				name="EVT-001",
				event_name="Test Event",
				event_date="2026-07-15",
				designation="Waiter",
				qty_required=3,
				qty_assigned=1,
			)
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


@patch("event_bookings.utils.scheduler.notify_managers_upcoming_events")
@patch("event_bookings.utils.scheduler.send_unstaffed_alerts")
@patch("event_bookings.utils.scheduler.sync_invoice_payment_status")
@patch("event_bookings.utils.scheduler.frappe")
class TestDaily(unittest.TestCase):
	def test_calls_all_subtasks(self, mock_frappe, mock_sync, mock_alert, mock_notify):

		daily()

		mock_sync.assert_called_once()
		mock_alert.assert_called_once()
		mock_notify.assert_called_once()
