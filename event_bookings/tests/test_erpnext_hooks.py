import unittest

import frappe
from event_bookings.tests.compat import FrappeTestCase
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from event_bookings.utils.erpnext_hooks import (
	validate_event_booking_link,
	on_quotation_cancel,
	on_quotation_submit,
	on_quotation_update,
	on_sales_invoice_cancel,
	on_sales_invoice_submit,
	on_sales_order_cancel,
	on_sales_order_submit,
	on_shift_assignment_update,
)


def _eb(docstatus=0):
	"""Minimal Event Booking stand-in returned by the mocked frappe.get_doc."""
	return SimpleNamespace(docstatus=docstatus, save=MagicMock())


# _update_linked_event_booking persists the link via frappe.db.set_value first
# (so it survives even if a later save() is blocked), then re-loads the booking
# and, for drafts, saves it.  These tests assert that contract.
#
# The fields go out as a single dict — one UPDATE for the whole set rather than
# one per field.


@patch("event_bookings.utils.erpnext_hooks.frappe")
class TestLinkOnSubmit(unittest.TestCase):
	def test_quotation_submit_sets_link(self, mock_frappe):
		mock_frappe.get_doc.return_value = _eb(docstatus=0)
		doc = SimpleNamespace(event_booking="EVT-001", name="QTN-001", doctype="Quotation")
		on_quotation_submit(doc, "on_submit")
		mock_frappe.db.set_value.assert_called_once_with(
			"Event Booking", "EVT-001", {"quotation": "QTN-001"}, update_modified=False
		)

	def test_sales_order_submit_sets_link(self, mock_frappe):
		mock_frappe.get_doc.return_value = _eb(docstatus=0)
		doc = SimpleNamespace(event_booking="EVT-001", name="SO-001", doctype="Sales Order")
		on_sales_order_submit(doc, "on_submit")
		mock_frappe.db.set_value.assert_called_once_with(
			"Event Booking", "EVT-001", {"sales_order": "SO-001"}, update_modified=False
		)

	def test_sales_invoice_submit_sets_link(self, mock_frappe):
		mock_frappe.get_doc.return_value = _eb(docstatus=0)
		doc = SimpleNamespace(event_booking="EVT-001", name="SINV-001", doctype="Sales Invoice")
		on_sales_invoice_submit(doc, "on_submit")
		mock_frappe.db.set_value.assert_called_once_with(
			"Event Booking", "EVT-001", {"sales_invoice": "SINV-001"}, update_modified=False
		)

	def test_skips_when_no_event_booking(self, mock_frappe):
		doc = SimpleNamespace(event_booking=None, name="QTN-002", doctype="Quotation")
		on_quotation_submit(doc, "on_submit")
		mock_frappe.db.set_value.assert_not_called()
		mock_frappe.get_doc.assert_not_called()


@patch("event_bookings.utils.erpnext_hooks.frappe")
class TestOnUpdate(unittest.TestCase):
	def test_quotation_update_sets_link_when_booking_present(self, mock_frappe):
		mock_frappe.get_doc.return_value = _eb(docstatus=0)
		doc = SimpleNamespace(event_booking="EVT-001", name="QTN-001", doctype="Quotation")
		on_quotation_update(doc, "on_update")
		mock_frappe.db.set_value.assert_called_once_with(
			"Event Booking", "EVT-001", {"quotation": "QTN-001"}, update_modified=False
		)

	def test_update_noop_without_booking(self, mock_frappe):
		doc = SimpleNamespace(event_booking=None, name="QTN-002", doctype="Quotation")
		on_quotation_update(doc, "on_update")
		mock_frappe.db.set_value.assert_not_called()


@patch("event_bookings.utils.erpnext_hooks.frappe")
class TestCancelHooks(unittest.TestCase):
	def test_quotation_cancel_unlinks(self, mock_frappe):
		mock_frappe.get_doc.return_value = _eb(docstatus=0)
		doc = SimpleNamespace(event_booking="EVT-001", name="QTN-001", doctype="Quotation")
		on_quotation_cancel(doc, "on_cancel")
		mock_frappe.db.set_value.assert_called_once_with(
			"Event Booking", "EVT-001", {"quotation": None}, update_modified=False
		)

	def test_sales_order_cancel_unlinks(self, mock_frappe):
		mock_frappe.get_doc.return_value = _eb(docstatus=0)
		doc = SimpleNamespace(event_booking="EVT-001", name="SO-001", doctype="Sales Order")
		on_sales_order_cancel(doc, "on_cancel")
		mock_frappe.db.set_value.assert_called_once_with(
			"Event Booking", "EVT-001", {"sales_order": None}, update_modified=False
		)

	def test_sales_invoice_cancel_unlinks(self, mock_frappe):
		mock_frappe.get_doc.return_value = _eb(docstatus=0)
		doc = SimpleNamespace(event_booking="EVT-001", name="SINV-001", doctype="Sales Invoice")
		on_sales_invoice_cancel(doc, "on_cancel")
		mock_frappe.db.set_value.assert_called_once_with(
			"Event Booking", "EVT-001", {"sales_invoice": None}, update_modified=False
		)


@patch("event_bookings.utils.erpnext_hooks.frappe")
class TestShiftAssignmentUpdate(unittest.TestCase):
	def test_recomputes_when_booking_present(self, mock_frappe):
		doc = SimpleNamespace(event_booking="EVT-001", name="HR-SA-001")
		on_shift_assignment_update(doc, "on_update")
		mock_frappe.db.sql.assert_called_once()
		args = mock_frappe.db.sql.call_args[0]
		self.assertIn("tabEvent Staff Requirement", args[0])
		# exclude_name is always bound now — the SQL is one fixed statement
		# rather than one assembled per path — and is empty except on trash,
		# where it names the row still sitting in the table.
		self.assertEqual(args[1], {"booking": "EVT-001", "exclude_name": ""})

	def test_trash_excludes_the_row_being_removed(self, mock_frappe):
		"""The trashed assignment is still in the table when the hook runs."""
		doc = SimpleNamespace(event_booking="EVT-001", name="HR-SA-009")
		on_shift_assignment_update(doc, "on_trash")
		args = mock_frappe.db.sql.call_args[0]
		self.assertEqual(args[1]["exclude_name"], "HR-SA-009")

	def test_noop_without_booking(self, mock_frappe):
		doc = SimpleNamespace(event_booking=None, name="HR-SA-002")
		on_shift_assignment_update(doc, "on_update")
		mock_frappe.db.sql.assert_not_called()


if __name__ == "__main__":
	unittest.main()


class TestEventBookingLinkGuard(FrappeTestCase):
	"""The event_booking link is the trust boundary for status automation.

	advance_booking_status writes with frappe.db.set_value, which bypasses
	permission_query_conditions by design — the submitter legitimately may not
	own the booking. So whoever can set the link can drive the booking's whole
	commercial lifecycle, and the link itself must be guarded.
	"""

	PROBE = "eb_link_guard_probe@example.com"

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("User Permission", {"user": self.PROBE})
		if frappe.db.exists("User", self.PROBE):
			frappe.delete_doc("User", self.PROBE, force=True, ignore_permissions=True)
		frappe.db.rollback()

	def _probe_restricted_to(self, company):
		if not frappe.db.exists("User", self.PROBE):
			user = frappe.get_doc({
				"doctype": "User", "email": self.PROBE, "first_name": "Link Guard Probe",
				"send_welcome_email": 0, "user_type": "System User",
			})
			user.insert(ignore_permissions=True)
			user.add_roles("Sales User")
		if not frappe.db.exists(
			"User Permission", {"user": self.PROBE, "allow": "Company", "for_value": company}
		):
			frappe.get_doc({
				"doctype": "User Permission", "user": self.PROBE,
				"allow": "Company", "for_value": company,
			}).insert(ignore_permissions=True)

	def test_cannot_link_a_booking_from_another_company(self):
		booking = frappe.db.get_value(
			"Event Booking", {"docstatus": ("<", 2)}, ["name", "company"], as_dict=True
		)
		if not booking:
			self.skipTest("no Event Booking on this site")
		other = frappe.db.get_value("Company", {"name": ("!=", booking.company)}, "name")
		if not other:
			self.skipTest("single-company site — nothing to cross")

		self._probe_restricted_to(other)
		forged = SimpleNamespace(
			event_booking=booking.name, company=other,
			doctype="Sales Invoice", name="SINV-FORGED",
			flags=SimpleNamespace(event_booking_inherited=False),
			is_new=lambda: True,
		)

		frappe.set_user(self.PROBE)
		try:
			self.assertFalse(
				frappe.has_permission("Event Booking", "read", booking.name),
				"probe must not be able to see the booking, or the test proves nothing",
			)
			with self.assertRaises(frappe.PermissionError):
				validate_event_booking_link(forged, "validate")
		finally:
			frappe.set_user("Administrator")

	def test_server_inherited_link_is_trusted(self):
		"""A link this app copies from a source document must never be blocked."""
		booking = frappe.db.get_value("Event Booking", {"docstatus": ("<", 2)}, "name")
		if not booking:
			self.skipTest("no Event Booking on this site")
		inherited = SimpleNamespace(
			event_booking=booking, company=None,
			doctype="Sales Invoice", name="SINV-INHERITED",
			flags=SimpleNamespace(event_booking_inherited=True),
			is_new=lambda: True,
		)
		validate_event_booking_link(inherited, "validate")  # must not raise


class TestPlannerPartitionOnSingleDocument(FrappeTestCase):
	"""permission_query_conditions constrains list and report queries only.

	Frappe consults has_permission for a single document, so a planner
	partition implemented in the query condition alone is list-only: the
	booking is hidden from the list view and still served by
	/api/resource/Event Booking/<name>.
	"""

	PROBE = "eb_planner_partition_probe@example.com"

	def tearDown(self):
		frappe.set_user("Administrator")
		# The probe user may have ToDos created by Frappe during the test
		# (e.g. on the booking). Deleting the user cascades to those ToDos,
		# which can hit MariaDB 1020 "Record has changed since last read"
		# because the rows were modified after the transaction's snapshot.
		# Commit first so the delete sees a consistent view, then rollback
		# the test's other changes (Sales Partner, event_planner mutation).
		try:
			frappe.db.commit()
			if frappe.db.exists("User", self.PROBE):
				frappe.delete_doc("User", self.PROBE, force=True, ignore_permissions=True)
		except Exception:
			pass
		frappe.db.rollback()

	def test_other_planners_booking_is_not_readable_by_name(self):
		booking = frappe.db.get_value(
			"Event Booking", {"docstatus": ("<", 2)}, ["name", "event_planner"], as_dict=True
		)
		if not booking:
			self.skipTest("no Event Booking on this site")

		owning = frappe.get_doc({
			"doctype": "Sales Partner",
			"partner_name": f"Owning {frappe.generate_hash(length=6)}",
			"commission_rate": 0,
		}).insert(ignore_permissions=True)
		frappe.db.set_value(
			"Event Booking", booking.name, "event_planner", owning.name, update_modified=False
		)

		# Guard the insert: a probe left behind by an interrupted run would
		# otherwise collide on the primary key and fail the test for the wrong
		# reason.
		if frappe.db.exists("User", self.PROBE):
			frappe.delete_doc("User", self.PROBE, force=True, ignore_permissions=True)
		user = frappe.get_doc({
			"doctype": "User", "email": self.PROBE, "first_name": "Planner Probe",
			"send_welcome_email": 0, "user_type": "System User",
		}).insert(ignore_permissions=True)
		user.add_roles("Event Manager")

		frappe.set_user(self.PROBE)
		try:
			names = [
				r.name for r in frappe.get_list(
					"Event Booking", fields=["name"], limit_page_length=0
				)
			]
			self.assertNotIn(
				booking.name, names, "query condition should already hide it from lists"
			)
			# The point of the test: the same must hold for direct access.
			self.assertFalse(
				frappe.has_permission("Event Booking", "read", booking.name),
				"a booking belonging to another planner was readable by name",
			)
		finally:
			frappe.set_user("Administrator")
