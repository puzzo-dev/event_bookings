"""Unit tests for EventBooking methods not covered by the integration tests.

These tests mock frappe so they can run without a live Frappe site.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from event_bookings.event_bookings.doctype.event_booking.event_booking import EventBooking


def _make_staff_req(**overrides):
	defaults = {
		"designation": "Waiter",
		"qty_required": 3,
		"qty_assigned": 0,
	}
	defaults.update(overrides)
	return defaults


def _new_booking(**overrides):
	"""Create a bare EventBooking instance without calling __init__."""
	eb = object.__new__(EventBooking)
	eb.staff_requirements = []
	eb.cost_center = None
	eb.total_estimated = 0
	eb.total_actual = 0
	eb.quotation = None
	eb.sales_order = None
	eb.sales_invoice = None
	eb.material_request = None
	eb.booking_status = "New"
	eb.party_type = "Customer"
	eb.party_name = "Test Customer"
	eb.event_name = "Test Event"
	eb.event_date = "2026-08-01"
	eb.event_location = "Venue"
	eb.name = "EVT-001"
	eb.flags = SimpleNamespace(ignore_permissions=False)
	for k, v in overrides.items():
		setattr(eb, k, v)
	return eb


# ── calculate_totals ────────────────────────────────────────────────


def _make_doc(items):
	"""Return a minimal fake document with an items child table."""
	doc = MagicMock()
	doc.items = [SimpleNamespace(amount=amt) for amt in items]
	return doc


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestCalculateTotals(unittest.TestCase):
	def test_no_linked_docs(self, mock_frappe):
		eb = _new_booking()
		eb.calculate_totals()
		self.assertEqual(eb.total_estimated, 0.0)
		self.assertEqual(eb.total_actual, 0.0)

	def test_from_quotation(self, mock_frappe):
		mock_frappe.get_doc.return_value = _make_doc([1200.0, 1300.0])
		eb = _new_booking(quotation="QTN-001")
		eb.calculate_totals()
		self.assertEqual(eb.total_estimated, 2500.0)
		self.assertEqual(eb.total_actual, 0.0)

	def test_from_sales_order(self, mock_frappe):
		mock_frappe.get_doc.side_effect = [
			_make_doc([1200.0, 1300.0]),  # quotation
			_make_doc([1500.0, 1500.0]),  # sales order
		]
		eb = _new_booking(quotation="QTN-001", sales_order="SO-001")
		eb.calculate_totals()
		self.assertEqual(eb.total_estimated, 2500.0)
		self.assertEqual(eb.total_actual, 3000.0)

	def test_from_sales_invoice_when_no_so(self, mock_frappe):
		mock_frappe.get_doc.return_value = _make_doc([2000.0, 2500.0])
		eb = _new_booking(sales_invoice="SI-001")
		eb.calculate_totals()
		self.assertEqual(eb.total_estimated, 0.0)
		self.assertEqual(eb.total_actual, 4500.0)

	def test_missing_linked_doc_returns_zero(self, mock_frappe):
		mock_frappe.get_doc.side_effect = Exception("Not found")
		eb = _new_booking(quotation="QTN-001")
		eb.calculate_totals()
		self.assertEqual(eb.total_estimated, 0.0)
		self.assertEqual(eb.total_actual, 0.0)


# ── validate_dates ──────────────────────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.today")
class TestValidateDates(unittest.TestCase):
	def test_past_date_new_booking_throws(self, mock_today, mock_frappe):
		mock_today.return_value = "2026-07-10"
		eb = _new_booking(event_date="2026-07-09")
		eb.is_new = lambda: True

		eb.validate_dates()
		mock_frappe.throw.assert_called_once()

	def test_past_date_existing_booking_no_throw(self, mock_today, mock_frappe):
		mock_today.return_value = "2026-07-10"
		eb = _new_booking(event_date="2026-07-09")
		eb.is_new = lambda: False

		eb.validate_dates()
		mock_frappe.throw.assert_not_called()

	def test_future_date_no_throw(self, mock_today, mock_frappe):
		mock_today.return_value = "2026-07-10"
		eb = _new_booking(event_date="2026-07-15")
		eb.is_new = lambda: True

		eb.validate_dates()
		mock_frappe.throw.assert_not_called()

	def test_none_date_no_throw(self, mock_today, mock_frappe):
		eb = _new_booking(event_date=None)
		eb.is_new = lambda: True

		eb.validate_dates()
		mock_frappe.throw.assert_not_called()


# ── set_defaults_from_settings / set_cost_center ────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestSetDefaults(unittest.TestCase):
	def test_sets_cost_center_from_settings(self, mock_frappe):
		settings = SimpleNamespace(default_cost_center="CC-001", auto_create_cost_center_per_event=False)
		mock_frappe.get_cached_doc.return_value = settings

		eb = _new_booking(cost_center=None)
		eb.set_defaults_from_settings()
		self.assertEqual(eb.cost_center, "CC-001")

	def test_preserves_existing_cost_center(self, mock_frappe):
		settings = SimpleNamespace(default_cost_center="CC-001", auto_create_cost_center_per_event=False)
		mock_frappe.get_cached_doc.return_value = settings

		eb = _new_booking(cost_center="CC-CUSTOM")
		eb.set_defaults_from_settings()
		self.assertEqual(eb.cost_center, "CC-CUSTOM")

	def test_set_cost_center_no_default(self, mock_frappe):
		settings = SimpleNamespace(default_cost_center=None)
		mock_frappe.get_cached_doc.return_value = settings

		eb = _new_booking(cost_center=None)
		eb.set_cost_center()
		self.assertIsNone(eb.cost_center)


# ── ensure_cost_center ────────────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestEnsureEventCostCenter(unittest.TestCase):
	def test_delegates_to_set_cost_center_when_auto_disabled(self, mock_frappe):
		settings = SimpleNamespace(auto_create_cost_center_per_event=False, default_cost_center="CC-001")
		mock_frappe.get_cached_doc.return_value = settings

		eb = _new_booking(cost_center=None)
		eb.ensure_cost_center()
		self.assertEqual(eb.cost_center, "CC-001")

	def test_skips_when_already_set(self, mock_frappe):
		settings = SimpleNamespace(auto_create_cost_center_per_event=True, default_cost_center="CC-001")
		mock_frappe.get_cached_doc.return_value = settings

		eb = _new_booking(cost_center="CC-EXISTING")
		eb.ensure_cost_center()
		self.assertEqual(eb.cost_center, "CC-EXISTING")

	def test_throws_when_no_parent_cc(self, mock_frappe):
		settings = SimpleNamespace(auto_create_cost_center_per_event=True, default_cost_center=None)
		mock_frappe.get_cached_doc.return_value = settings

		eb = _new_booking(cost_center=None)
		eb.ensure_cost_center()
		mock_frappe.throw.assert_called_once()

	def test_creates_new_cost_center(self, mock_frappe):
		settings = SimpleNamespace(auto_create_cost_center_per_event=True, default_cost_center="Parent CC")
		mock_frappe.get_cached_doc.return_value = settings
		mock_frappe.db.exists.return_value = False
		mock_frappe.db.get_value.side_effect = ["Test Co", "TC"]

		mock_cc = MagicMock()
		mock_cc.name = "EVT-001 - Test Event - TC"
		mock_frappe.get_doc.return_value = mock_cc

		eb = _new_booking(cost_center=None, name="EVT-001", event_name="Test Event")
		eb.ensure_cost_center()

		mock_frappe.get_doc.assert_called_once()
		call_args = mock_frappe.get_doc.call_args[0][0]
		self.assertEqual(call_args["doctype"], "Cost Center")
		self.assertEqual(call_args["parent_cost_center"], "Parent CC")
		mock_cc.insert.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(eb.cost_center, "EVT-001 - Test Event - TC")

	def test_reuses_existing_cost_center(self, mock_frappe):
		settings = SimpleNamespace(auto_create_cost_center_per_event=True, default_cost_center="Parent CC")
		mock_frappe.get_cached_doc.return_value = settings
		mock_frappe.db.exists.return_value = True
		mock_frappe.db.get_value.side_effect = ["Test Co", "TC"]

		eb = _new_booking(cost_center=None, name="EVT-001", event_name="Test Event")
		eb.ensure_cost_center()

		mock_frappe.get_doc.assert_not_called()
		self.assertEqual(eb.cost_center, "EVT-001 - Test Event - TC")


# ── has_status_changed ──────────────────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestHasStatusChanged(unittest.TestCase):
	def test_new_doc_returns_false(self, mock_frappe):
		eb = _new_booking()
		eb.is_new = lambda: True
		self.assertFalse(eb.has_status_changed())

	def test_same_status_returns_false(self, mock_frappe):
		mock_frappe.db.get_value.return_value = "New"
		eb = _new_booking(booking_status="New")
		eb.is_new = lambda: False
		self.assertFalse(eb.has_status_changed())

	def test_different_status_returns_true(self, mock_frappe):
		mock_frappe.db.get_value.return_value = "New"
		eb = _new_booking(booking_status="Quoted")
		eb.is_new = lambda: False
		self.assertTrue(eb.has_status_changed())


# ── handle_status_transition ────────────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestHandleStatusTransition(unittest.TestCase):
	def test_quoted_creates_quotation(self, mock_frappe):
		eb = _new_booking(booking_status="Quoted")
		eb.create_quotation = MagicMock()
		eb.handle_status_transition()
		eb.create_quotation.assert_called_once()

	def test_confirmed_ensures_cost_center(self, mock_frappe):
		eb = _new_booking(booking_status="Confirmed")
		eb.ensure_cost_center = MagicMock()
		eb.handle_status_transition()
		eb.ensure_cost_center.assert_called_once()

	def test_in_preparation_creates_shifts(self, mock_frappe):
		eb = _new_booking(booking_status="In Preparation")
		eb.create_shift_assignments = MagicMock()
		eb.handle_status_transition()
		eb.create_shift_assignments.assert_called_once()

	def test_executed_is_noop(self, mock_frappe):
		eb = _new_booking(booking_status="Executed")
		eb.handle_status_transition()

	def test_invoiced_is_noop(self, mock_frappe):
		eb = _new_booking(booking_status="Invoiced")
		eb.handle_status_transition()

	def test_paid_is_noop(self, mock_frappe):
		eb = _new_booking(booking_status="Paid")
		eb.handle_status_transition()


# ── create_quotation ────────────────────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestCreateQuotation(unittest.TestCase):
	def test_skips_when_quotation_exists(self, mock_frappe):
		eb = _new_booking(quotation="QTN-001")
		eb.create_quotation()
		mock_frappe.get_doc.assert_not_called()

	def test_builds_blank_quotation(self, mock_frappe):
		settings = SimpleNamespace(
			default_cost_center="CC-001",
		)
		mock_frappe.get_cached_doc.return_value = settings

		mock_qt = MagicMock()
		mock_qt.name = "QTN-NEW"
		mock_frappe.get_doc.return_value = mock_qt

		mock_frappe.get_installed_apps.return_value = ["frappe", "erpnext"]
		eb = _new_booking(
			party_type="Customer",
			party_name="Acme",
			cost_center="CC-EVT",
			quotation=None,
		)
		eb.create_quotation()

		mock_frappe.get_doc.assert_called_once()
		call_args = mock_frappe.get_doc.call_args[0][0]
		self.assertEqual(call_args["quotation_to"], "Customer")
		self.assertEqual(call_args["party_name"], "Acme")
		mock_qt.insert.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(eb.quotation, "QTN-NEW")


# ── create_shift_assignments ────────────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestCreateShiftAssignments(unittest.TestCase):
	def test_creates_shift_per_unassigned_slot(self, mock_frappe):
		mock_frappe.get_installed_apps.return_value = ["frappe", "hrms"]
		settings = SimpleNamespace(default_shift_type="Morning")
		mock_frappe.get_cached_doc.return_value = settings
		mock_frappe.db.count.return_value = 0

		mock_shift = MagicMock()
		mock_frappe.get_doc.return_value = mock_shift

		req = _make_staff_req(designation="Waiter", qty_required=3, qty_assigned=0)
		eb = _new_booking(staff_requirements=[req], event_date="2026-08-01")
		eb.create_shift_assignments()

		self.assertEqual(mock_frappe.get_doc.call_count, 3)
		self.assertEqual(mock_shift.insert.call_count, 3)

	def test_creates_only_needed_shifts(self, mock_frappe):
		mock_frappe.get_installed_apps.return_value = ["frappe", "hrms"]
		settings = SimpleNamespace(default_shift_type="Morning")
		mock_frappe.get_cached_doc.return_value = settings
		mock_frappe.db.count.return_value = 2

		mock_shift = MagicMock()
		mock_frappe.get_doc.return_value = mock_shift

		req = _make_staff_req(designation="Chef", qty_required=3, qty_assigned=2)
		eb = _new_booking(staff_requirements=[req])
		eb.create_shift_assignments()

		self.assertEqual(mock_frappe.get_doc.call_count, 1)

	def test_no_shifts_when_fully_staffed(self, mock_frappe):
		mock_frappe.get_installed_apps.return_value = ["frappe", "hrms"]
		settings = SimpleNamespace(default_shift_type="Morning")
		mock_frappe.get_cached_doc.return_value = settings
		mock_frappe.db.count.return_value = 5

		req = _make_staff_req(qty_required=5, qty_assigned=5)
		eb = _new_booking(staff_requirements=[req])
		eb.create_shift_assignments()

		mock_frappe.get_doc.assert_not_called()

	def test_skips_when_hrms_not_installed(self, mock_frappe):
		mock_frappe.get_installed_apps.return_value = ["frappe"]
		req = _make_staff_req(qty_required=3, qty_assigned=0)
		eb = _new_booking(staff_requirements=[req])
		eb.create_shift_assignments()
		mock_frappe.get_doc.assert_not_called()


# ── update_staff_assignment_counts ──────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestUpdateStaffAssignmentCounts(unittest.TestCase):
	def test_updates_counts_from_db(self, mock_frappe):
		mock_frappe.db.sql.return_value = [{"designation": "Waiter", "cnt": 4}]

		req = _make_staff_req(designation="Waiter", qty_assigned=0)
		eb = _new_booking(staff_requirements=[req], name="EVT-001")
		eb.update_staff_assignment_counts()

		self.assertEqual(req["qty_assigned"], 4)
		mock_frappe.db.sql.assert_called_once()
		call_args = mock_frappe.db.sql.call_args
		self.assertEqual(call_args[0][1], "EVT-001")

	def test_multiple_requirements(self, mock_frappe):
		mock_frappe.db.sql.return_value = [
			{"designation": "Waiter", "cnt": 2},
			{"designation": "Chef", "cnt": 5},
		]

		r1 = _make_staff_req(designation="Waiter")
		r2 = _make_staff_req(designation="Chef")
		eb = _new_booking(staff_requirements=[r1, r2])
		eb.update_staff_assignment_counts()

		self.assertEqual(r1["qty_assigned"], 2)
		self.assertEqual(r2["qty_assigned"], 5)


# ── get_company_from_cost_center ────────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestGetCompanyFromCostCenter(unittest.TestCase):
	def test_returns_company_from_db(self, mock_frappe):
		mock_frappe.db.get_value.return_value = "Acme Ltd"

		eb = _new_booking()
		result = eb.get_company_from_cost_center("CC-001")

		mock_frappe.db.get_value.assert_called_once_with("Cost Center", "CC-001", "company")
		self.assertEqual(result, "Acme Ltd")

	def test_falls_back_to_default_company(self, mock_frappe):
		mock_frappe.db.get_value.return_value = None
		mock_frappe.defaults.get_defaults.return_value = {"company": "Default Co"}

		eb = _new_booking()
		result = eb.get_company_from_cost_center("CC-UNKNOWN")

		self.assertEqual(result, "Default Co")
