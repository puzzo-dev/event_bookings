"""Cancelling a document has to walk the booking back.

advance_booking_status is forward-only by design, so nothing undid a
transition: a booking that reached Paid on the strength of an invoice stayed
Paid after that invoice was cancelled, and every report counted revenue that
had been cancelled.
"""

import unittest
from unittest.mock import patch

import frappe

from event_bookings.tests.compat import FrappeTestCase
from event_bookings.utils.status import justified_status, revert_booking_status

_MOD = "event_bookings.utils.status"


class TestJustifiedStatus(unittest.TestCase):
	"""What the remaining live documents support, read backwards."""

	def _justified(self, links, si=None, so_submitted=True, qtn_submitted=True):
		def _get_value(doctype, name, fields=None, **kw):
			if doctype == "Event Booking":
				# get_value returns every requested key, present or not — a
				# booking with nothing linked is a dict of Nones, not an empty
				# one, and the two must not be confused with a missing booking.
				row = {"quotation": None, "sales_order": None, "sales_invoice": None}
				row.update(links)
				return frappe._dict(row)
			if doctype == "Sales Invoice":
				return frappe._dict(si or {})
			if doctype == "Sales Order":
				return 1 if so_submitted else 2
			if doctype == "Quotation":
				return 1 if qtn_submitted else 2
			return None

		with patch(f"{_MOD}.frappe.db.get_value", side_effect=_get_value):
			return justified_status("EVT-1")

	def test_fully_paid_invoice_justifies_paid(self):
		self.assertEqual(
			self._justified({"sales_invoice": "SI-1"},
			                si={"docstatus": 1, "grand_total": 100, "outstanding_amount": 0}),
			"Paid",
		)

	def test_part_paid_invoice_justifies_confirmed(self):
		self.assertEqual(
			self._justified({"sales_invoice": "SI-1"},
			                si={"docstatus": 1, "grand_total": 100, "outstanding_amount": 40}),
			"Confirmed",
		)

	def test_unpaid_invoice_justifies_invoiced(self):
		self.assertEqual(
			self._justified({"sales_invoice": "SI-1"},
			                si={"docstatus": 1, "grand_total": 100, "outstanding_amount": 100}),
			"Invoiced",
		)

	def test_cancelled_invoice_falls_through_to_the_order(self):
		self.assertEqual(
			self._justified({"sales_invoice": "SI-1", "sales_order": "SO-1"},
			                si={"docstatus": 2, "grand_total": 100, "outstanding_amount": 0}),
			"Confirmed",
		)

	def test_only_a_quotation_justifies_quoted(self):
		self.assertEqual(self._justified({"quotation": "Q-1"}), "Quoted")

	def test_nothing_live_justifies_new(self):
		self.assertEqual(self._justified({}), "New")

	def test_a_missing_booking_is_not_new(self):
		"""None means "no such booking"; New is a real answer about a real one."""
		with patch(f"{_MOD}.frappe.db.get_value", return_value=None):
			self.assertIsNone(justified_status("EVT-GONE"))


class TestRevertBookingStatus(FrappeTestCase):
	"""Backwards only, and never past the states that must not move."""

	def tearDown(self):
		frappe.db.rollback()

	def _revert(self, current, justified, docstatus=1):
		with patch(f"{_MOD}.frappe.db.get_value",
		           return_value=frappe._dict(status=current, docstatus=docstatus)), \
			patch(f"{_MOD}.justified_status", return_value=justified), \
			patch(f"{_MOD}.automation_enabled", return_value=True), \
			patch(f"{_MOD}.frappe.db.set_value") as set_value, \
			patch(f"{_MOD}._add_timeline_comment"):
			changed = revert_booking_status("EVT-1", reason="probe")
		return changed, set_value

	def test_moves_back_when_the_documents_no_longer_support_it(self):
		changed, set_value = self._revert("Paid", "Invoiced")
		self.assertTrue(changed)
		set_value.assert_called_once_with(
			"Event Booking", "EVT-1", {"status": "Invoiced"}
		)

	def test_never_moves_forward(self):
		"""Going forwards stays advance_booking_status's job."""
		changed, set_value = self._revert("Invoiced", "Paid")
		self.assertFalse(changed)
		set_value.assert_not_called()

	def test_no_change_when_already_correct(self):
		changed, _ = self._revert("Invoiced", "Invoiced")
		self.assertFalse(changed)

	def test_executed_is_terminal(self):
		"""Cancelling paperwork does not un-happen the event."""
		changed, _ = self._revert("Executed", "New")
		self.assertFalse(changed)

	def test_cancelled_booking_is_left_alone(self):
		changed, _ = self._revert("Cancelled", "New")
		self.assertFalse(changed)

	def test_cancelled_docstatus_is_left_alone(self):
		changed, _ = self._revert("Paid", "New", docstatus=2)
		self.assertFalse(changed)


if __name__ == "__main__":
	unittest.main()
