"""Unit tests for EventBooking methods.

These tests mock frappe so they can run without a live Frappe site.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from event_bookings.event_bookings.doctype.event_booking.event_booking import EventBooking


def _make_staff_req(**overrides):
	defaults = {
		"designation": "Waiter",
		"qty_required": 3,
		"qty_assigned": 0,
	}
	defaults.update(overrides)
	return SimpleNamespace(**defaults)


def _new_booking(**overrides):
	"""Create a bare EventBooking instance without calling __init__."""
	eb = object.__new__(EventBooking)
	eb.staff_requirements = []
	eb.event_cost_center = None
	eb.total_estimated = 0
	eb.damage_cost = 0
	eb.quotation = None
	eb.sales_order = None
	eb.sales_invoice = None
	eb.material_request = None
	eb.booking_status = "New"
	eb.customer = "Test Customer"
	eb.event_name = "Test Event"
	eb.event_date = "2026-08-01"
	eb.event_location = "Venue"
	eb.name = "EVT-001"
	eb.flags = SimpleNamespace(ignore_permissions=False)
	for k, v in overrides.items():
		setattr(eb, k, v)
	return eb


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


# ── set_defaults_from_settings ──────────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestSetDefaults(unittest.TestCase):
	def test_sets_cost_center_from_settings(self, mock_frappe):
		settings = SimpleNamespace(
			default_cost_center="CC-001",
			auto_create_cost_center_per_event=False,
		)
		mock_frappe.get_cached_doc.return_value = settings

		eb = _new_booking(event_cost_center=None)
		eb.set_defaults_from_settings()
		self.assertEqual(eb.event_cost_center, "CC-001")

	def test_preserves_existing_cost_center(self, mock_frappe):
		settings = SimpleNamespace(
			default_cost_center="CC-001",
			auto_create_cost_center_per_event=False,
		)
		mock_frappe.get_cached_doc.return_value = settings

		eb = _new_booking(event_cost_center="CC-CUSTOM")
		eb.set_defaults_from_settings()
		self.assertEqual(eb.event_cost_center, "CC-CUSTOM")

	def test_skips_when_auto_create_enabled(self, mock_frappe):
		settings = SimpleNamespace(
			default_cost_center="CC-001",
			auto_create_cost_center_per_event=True,
		)
		mock_frappe.get_cached_doc.return_value = settings

		eb = _new_booking(event_cost_center=None)
		eb.set_defaults_from_settings()
		self.assertIsNone(eb.event_cost_center)

	def test_no_default_cost_center(self, mock_frappe):
		settings = SimpleNamespace(
			default_cost_center=None,
			auto_create_cost_center_per_event=False,
		)
		mock_frappe.get_cached_doc.return_value = settings

		eb = _new_booking(event_cost_center=None)
		eb.set_defaults_from_settings()
		self.assertIsNone(eb.event_cost_center)


# ── ensure_event_cost_center ────────────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestEnsureEventCostCenter(unittest.TestCase):
	def test_delegates_to_set_defaults_when_auto_disabled(self, mock_frappe):
		settings = SimpleNamespace(
			auto_create_cost_center_per_event=False,
			default_cost_center="CC-001",
		)
		mock_frappe.get_cached_doc.return_value = settings

		eb = _new_booking(event_cost_center=None)
		eb.ensure_event_cost_center()
		self.assertEqual(eb.event_cost_center, "CC-001")

	def test_skips_when_already_set(self, mock_frappe):
		settings = SimpleNamespace(auto_create_cost_center_per_event=True, default_cost_center="CC-001")
		mock_frappe.get_cached_doc.return_value = settings

		eb = _new_booking(event_cost_center="CC-EXISTING")
		eb.ensure_event_cost_center()
		self.assertEqual(eb.event_cost_center, "CC-EXISTING")

	def test_throws_when_no_parent_cc(self, mock_frappe):
		settings = SimpleNamespace(auto_create_cost_center_per_event=True, default_cost_center=None)
		mock_frappe.get_cached_doc.return_value = settings

		eb = _new_booking(event_cost_center=None)
		eb.ensure_event_cost_center()
		mock_frappe.throw.assert_called_once()

	def test_creates_new_cost_center(self, mock_frappe):
		settings = SimpleNamespace(auto_create_cost_center_per_event=True, default_cost_center="Parent CC")
		mock_frappe.get_cached_doc.return_value = settings
		mock_frappe.db.exists.return_value = False

		def db_get_value(doctype, name, field=None, **kw):
			if doctype == "Cost Center":
				return "Test Co"
			if doctype == "Company":
				return "TC"
			return None

		mock_frappe.db.get_value.side_effect = db_get_value

		mock_cc = MagicMock()
		mock_cc.name = "EVT-001 - Test Event - TC"
		mock_frappe.get_doc.return_value = mock_cc

		eb = _new_booking(event_cost_center=None, name="EVT-001", event_name="Test Event")
		eb.ensure_event_cost_center()

		mock_frappe.get_doc.assert_called_once()
		call_args = mock_frappe.get_doc.call_args[0][0]
		self.assertEqual(call_args["doctype"], "Cost Center")
		self.assertEqual(call_args["parent_cost_center"], "Parent CC")
		mock_cc.insert.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(eb.event_cost_center, "EVT-001 - Test Event - TC")

	def test_reuses_existing_cost_center(self, mock_frappe):
		settings = SimpleNamespace(auto_create_cost_center_per_event=True, default_cost_center="Parent CC")
		mock_frappe.get_cached_doc.return_value = settings
		mock_frappe.db.exists.return_value = True

		def db_get_value(doctype, name, field=None, **kw):
			if doctype == "Cost Center":
				return "Test Co"
			if doctype == "Company":
				return "TC"
			return None

		mock_frappe.db.get_value.side_effect = db_get_value

		eb = _new_booking(event_cost_center=None, name="EVT-001", event_name="Test Event")
		eb.ensure_event_cost_center()

		mock_frappe.get_doc.assert_not_called()
		self.assertEqual(eb.event_cost_center, "EVT-001 - Test Event - TC")


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
	def test_confirmed_ensures_cost_center(self, mock_frappe):
		eb = _new_booking(booking_status="Confirmed")
		eb.ensure_event_cost_center = MagicMock()
		eb.handle_status_transition()
		eb.ensure_event_cost_center.assert_called_once()

	def test_in_preparation_creates_shifts(self, mock_frappe):
		eb = _new_booking(booking_status="In Preparation")
		eb.create_shift_assignments = MagicMock()
		eb.handle_status_transition()
		eb.create_shift_assignments.assert_called_once()

	def test_executed_is_noop(self, mock_frappe):
		eb = _new_booking(booking_status="Executed")
		eb.handle_status_transition()

	def test_invoiced_creates_sales_invoice(self, mock_frappe):
		eb = _new_booking(booking_status="Invoiced")
		eb.create_sales_invoice = MagicMock()
		eb.handle_status_transition()
		eb.create_sales_invoice.assert_called_once()

	def test_cancelled_runs_cancellation(self, mock_frappe):
		eb = _new_booking(booking_status="Cancelled")
		eb.handle_cancellation = MagicMock()
		eb.handle_status_transition()
		eb.handle_cancellation.assert_called_once()

	def test_paid_is_noop(self, mock_frappe):
		eb = _new_booking(booking_status="Paid")
		eb.handle_status_transition()


# ── create_shift_assignments ────────────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestCreateShiftAssignments(unittest.TestCase):
	def test_creates_shift_per_unassigned_slot(self, mock_frappe):
		settings = SimpleNamespace(default_shift_type="Morning")
		mock_frappe.get_cached_doc.return_value = settings
		mock_frappe.db.count.return_value = 0
		mock_frappe.utils.flt.side_effect = lambda x: float(x or 0)

		mock_shift = MagicMock()
		mock_frappe.get_doc.return_value = mock_shift

		req = _make_staff_req(designation="Waiter", qty_required=3, qty_assigned=0)
		eb = _new_booking(staff_requirements=[req], event_date="2026-08-01")
		eb.create_shift_assignments()

		self.assertEqual(mock_frappe.get_doc.call_count, 3)
		self.assertEqual(mock_shift.insert.call_count, 3)

	def test_creates_only_needed_shifts(self, mock_frappe):
		settings = SimpleNamespace(default_shift_type="Morning")
		mock_frappe.get_cached_doc.return_value = settings
		mock_frappe.db.count.return_value = 2
		mock_frappe.utils.flt.side_effect = lambda x: float(x or 0)

		mock_shift = MagicMock()
		mock_frappe.get_doc.return_value = mock_shift

		req = _make_staff_req(designation="Chef", qty_required=3, qty_assigned=2)
		eb = _new_booking(staff_requirements=[req])
		eb.create_shift_assignments()

		self.assertEqual(mock_frappe.get_doc.call_count, 1)

	def test_no_shifts_when_fully_staffed(self, mock_frappe):
		settings = SimpleNamespace(default_shift_type="Morning")
		mock_frappe.get_cached_doc.return_value = settings
		mock_frappe.db.count.return_value = 5
		mock_frappe.utils.flt.side_effect = lambda x: float(x or 0)

		req = _make_staff_req(qty_required=5, qty_assigned=5)
		eb = _new_booking(staff_requirements=[req])
		eb.create_shift_assignments()

		mock_frappe.get_doc.assert_not_called()


# ── update_staff_assignment_counts ──────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestUpdateStaffAssignmentCounts(unittest.TestCase):
	def test_updates_counts_from_db(self, mock_frappe):
		mock_frappe.db.count.return_value = 4

		req = _make_staff_req(designation="Waiter", qty_assigned=0)
		eb = _new_booking(staff_requirements=[req], name="EVT-001")
		eb.update_staff_assignment_counts()

		self.assertEqual(req.qty_assigned, 4)
		mock_frappe.db.count.assert_called_once_with(
			"Shift Assignment",
			filters={
				"event_booking": "EVT-001",
				"designation": "Waiter",
				"docstatus": ("<", 2),
			},
		)

	def test_multiple_requirements(self, mock_frappe):
		mock_frappe.db.count.side_effect = [2, 5]

		r1 = _make_staff_req(designation="Waiter")
		r2 = _make_staff_req(designation="Chef")
		eb = _new_booking(staff_requirements=[r1, r2])
		eb.update_staff_assignment_counts()

		self.assertEqual(r1.qty_assigned, 2)
		self.assertEqual(r2.qty_assigned, 5)


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


# ── create_sales_invoice ────────────────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestCreateSalesInvoice(unittest.TestCase):
	def test_skips_when_si_exists(self, mock_frappe):
		eb = _new_booking(sales_invoice="SI-001", sales_order="SO-001")
		eb.create_sales_invoice()
		mock_frappe.get_doc.assert_not_called()

	def test_warns_when_no_sales_order(self, mock_frappe):
		eb = _new_booking(sales_invoice=None, sales_order=None)
		eb.create_sales_invoice()
		mock_frappe.msgprint.assert_called_once()

	def test_creates_si_from_sales_order(self, mock_frappe):
		so_item = SimpleNamespace(
			item_code="ITEM-001",
			item_name="Chairs",
			qty=10,
			rate=100,
			amount=1000,
			name="SOI-001",
		)
		mock_so = MagicMock()
		mock_so.items = [so_item]

		mock_si = MagicMock()
		mock_si.name = "SI-NEW"

		def get_doc_side_effect(*args):
			if len(args) == 1 and isinstance(args[0], dict):
				return mock_si
			if len(args) >= 1 and args[0] == "Sales Order":
				return mock_so
			return MagicMock()

		mock_frappe.get_doc.side_effect = get_doc_side_effect

		eb = _new_booking(
			sales_invoice=None,
			sales_order="SO-001",
			event_cost_center="CC-001",
		)
		eb.create_sales_invoice()

		mock_si.insert.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(eb.sales_invoice, "SI-NEW")


# ── handle_cancellation ────────────────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestHandleCancellation(unittest.TestCase):
	def test_cancels_linked_docs(self, mock_frappe):
		mock_doc = MagicMock()
		mock_doc.docstatus = 1
		mock_frappe.get_doc.return_value = mock_doc
		mock_frappe.get_all.return_value = []

		eb = _new_booking(
			quotation="QUO-001",
			sales_order="SO-001",
			sales_invoice="SI-001",
			material_request="MR-001",
		)
		eb.handle_cancellation()

		self.assertEqual(mock_doc.cancel.call_count, 4)

	def test_releases_shift_assignments(self, mock_frappe):
		mock_frappe.get_all.return_value = ["SA-001", "SA-002"]

		draft_shift = MagicMock()
		draft_shift.docstatus = 0
		mock_frappe.get_doc.return_value = draft_shift

		eb = _new_booking(
			quotation=None,
			sales_order=None,
			sales_invoice=None,
			material_request=None,
		)
		eb.handle_cancellation()

		self.assertEqual(mock_frappe.delete_doc.call_count, 2)

	def test_handles_no_linked_docs(self, mock_frappe):
		mock_frappe.get_all.return_value = []

		eb = _new_booking(
			quotation=None,
			sales_order=None,
			sales_invoice=None,
			material_request=None,
		)
		eb.handle_cancellation()
		mock_frappe.log_error.assert_not_called()


# ── create_damage_stock_entry ──────────────────────────────────────


@patch("event_bookings.event_bookings.doctype.event_booking.event_booking.frappe")
class TestCreateDamageStockEntry(unittest.TestCase):
	def test_creates_stock_entry(self, mock_frappe):
		settings = SimpleNamespace(
			damage_warehouse="Damage WH",
			default_warehouse="Default WH",
			default_damage_account="Damage Acc",
		)
		mock_frappe.get_cached_doc.return_value = settings
		mock_frappe.db.get_value.return_value = 500

		se_items = []
		mock_se = MagicMock()
		mock_se.items = se_items
		mock_se.append.side_effect = lambda field, item: se_items.append(item)
		mock_frappe.get_doc.return_value = mock_se

		eb = _new_booking(event_cost_center="CC-001", damage_cost=0)
		eb.create_damage_stock_entry(
			[
				{"item_code": "CHAIR-001", "qty_damaged": 2, "rate": 100},
			]
		)

		mock_se.insert.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(eb.damage_cost, 200)

	def test_skips_zero_qty(self, mock_frappe):
		settings = SimpleNamespace(
			damage_warehouse="Damage WH",
			default_warehouse="Default WH",
			default_damage_account="Damage Acc",
		)
		mock_frappe.get_cached_doc.return_value = settings

		se_items = []
		mock_se = MagicMock()
		mock_se.items = se_items
		mock_se.append.side_effect = lambda field, item: se_items.append(item)
		mock_frappe.get_doc.return_value = mock_se

		eb = _new_booking(event_cost_center="CC-001", damage_cost=0)
		eb.create_damage_stock_entry(
			[
				{"item_code": "CHAIR-001", "qty_damaged": 0},
			]
		)

		mock_frappe.msgprint.assert_called_once()

	def test_throws_without_warehouse(self, mock_frappe):
		settings = SimpleNamespace(
			damage_warehouse=None,
			default_warehouse=None,
			default_damage_account=None,
		)
		mock_frappe.get_cached_doc.return_value = settings

		eb = _new_booking()
		eb.create_damage_stock_entry([{"item_code": "X", "qty_damaged": 1}])
		mock_frappe.throw.assert_called_once()
