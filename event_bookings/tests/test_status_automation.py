"""Status automation tests (Phase 1).

Covers:
- the automation matrix (quotation linked/submitted → Quoted; SI submitted →
  Invoiced; SI paid → Paid; event date passed → Executed),
- the forward-only guard (automation never downgrades),
- Cancelled / docstatus-2 bookings are never touched,
- the enable_automated_status and auto_executed_after_event_date toggles,
- automation on submitted bookings (booking_status is allow_on_submit),
- docstatus cancel cascading to linked documents synchronously (before_cancel
  runs ahead of Frappe's back-link check),
- the scheduler draft-booking fix (docstatus < 2, P1-16),
- the legacy-upgrade regression (P1-19): bookings in every pre-upgrade status
  are only ever changed per the matrix — no unintended rewrites.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe
from event_bookings.tests.compat import FrappeTestCase

from event_bookings.tests.fixtures import (
	ensure_test_customer_leaf_details,
	get_or_create_test_event_type,
	get_or_create_test_item,
	get_or_create_test_party,
)
from event_bookings.utils.erpnext_hooks import (
	_eb_advance_from_sales_invoice,
	on_quotation_submit,
	on_quotation_update,
	on_sales_invoice_submit,
	on_sales_invoice_update,
)
from event_bookings.utils.scheduler import (
	auto_execute_passed_events,
)
from event_bookings.utils.status import (
	CANCELLED,
	STATUS_ORDER,
	advance_booking_status,
	is_forward_transition,
)

ERPNEXT_INSTALLED = "erpnext" in frappe.get_installed_apps()


def _make_booking(**kwargs):
	"""Build a minimal insertable Event Booking using shared fixtures."""
	party_type, party_name = get_or_create_test_party()
	defaults = {
		"doctype": "Event Booking",
		"customer": party_name if party_type == "Customer" else None,
		"booking_status": "New",
		"booking_date": frappe.utils.today(),
		"event_time": "10:00:00",
		"event_location": "Test Venue",
		"event_date": frappe.utils.add_days(frappe.utils.today(), 30),
		"event_type": get_or_create_test_event_type(),
	}
	defaults.update(kwargs)
	return frappe.get_doc(defaults)


def _insert(**kwargs):
	doc = _make_booking(**kwargs)
	doc.insert(ignore_permissions=True)
	return doc


def _status(name):
	return frappe.db.get_value("Event Booking", name, "booking_status")


def _set_toggle(fieldname, value):
	frappe.db.set_single_value("Event Booking Settings", fieldname, value)
	frappe.clear_document_cache("Event Booking Settings", "Event Booking Settings")


@unittest.skipUnless(ERPNEXT_INSTALLED, "bookings require ERPNext (quotation-first flow)")
class TestForwardOnlyGuard(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_is_forward_transition_matrix(self):
		forward = [
			("New", "Quoted"),
			("Quoted", "Invoiced"),
			("Invoiced", "Confirmed"),
			("Confirmed", "Paid"),
			("Paid", "Executed"),
			("New", "Executed"),
		]
		for current, target in forward:
			self.assertTrue(is_forward_transition(current, target), (current, target))

		backward = [
			("Quoted", "New"),
			("Invoiced", "Quoted"),
			("Confirmed", "Invoiced"),
			("Paid", "Confirmed"),
			("Executed", "Paid"),
			("Executed", "New"),
		]
		for current, target in backward:
			self.assertFalse(is_forward_transition(current, target), (current, target))

		# Cancelled participates in no forward transitions (either side)
		self.assertFalse(is_forward_transition("Confirmed", CANCELLED))
		self.assertFalse(is_forward_transition(CANCELLED, "Executed"))

	def test_advance_never_downgrades(self):
		doc = _insert(event_name="Test No Downgrade", booking_status="Invoiced")
		self.assertFalse(advance_booking_status(doc.name, "Quoted"))
		self.assertEqual(_status(doc.name), "Invoiced")

		# The quotation-linked hook must not pull an Invoiced booking back
		on_quotation_update(
			SimpleNamespace(event_booking=doc.name, name="QTN-FAKE", doctype="Quotation"),
			None,
		)
		self.assertEqual(_status(doc.name), "Invoiced")

	def test_advance_skips_cancelled_and_unknown(self):
		doc = _insert(event_name="Test Cancelled Skip", booking_status=CANCELLED)
		self.assertFalse(advance_booking_status(doc.name, "Invoiced"))
		self.assertEqual(_status(doc.name), CANCELLED)

		doc2 = _insert(event_name="Test Unknown Target", booking_status="New")
		self.assertFalse(advance_booking_status(doc2.name, "Bogus"))
		self.assertFalse(advance_booking_status(None, "Quoted"))
		self.assertFalse(advance_booking_status(doc2.name, CANCELLED))
		self.assertEqual(_status(doc2.name), "New")

	def test_advance_skips_docstatus_cancelled(self):
		doc = _insert(event_name="Test DS2 Skip", booking_status="Confirmed")
		doc.submit()
		doc.cancel()
		self.assertEqual(doc.docstatus, 2)
		self.assertFalse(advance_booking_status(doc.name, "Executed"))


@unittest.skipUnless(ERPNEXT_INSTALLED, "bookings require ERPNext (quotation-first flow)")
class TestAdvanceBehaviour(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_advance_persists_and_audits(self):
		doc = _insert(event_name="Test Advance Audit", booking_status="New")
		self.assertTrue(advance_booking_status(doc.name, "Quoted", reason="test"))
		self.assertEqual(_status(doc.name), "Quoted")
		comments = frappe.get_all(
			"Comment",
			filters={
				"reference_doctype": "Event Booking",
				"reference_name": doc.name,
				"comment_type": "Comment",
			},
			pluck="name",
		)
		self.assertTrue(comments, "expected an audit timeline comment")

	def test_advance_respects_toggle(self):
		doc = _insert(event_name="Test Toggle Off", booking_status="New")
		_set_toggle("enable_automated_status", 0)
		try:
			self.assertFalse(advance_booking_status(doc.name, "Quoted"))
			self.assertEqual(_status(doc.name), "New")
		finally:
			_set_toggle("enable_automated_status", 1)
		self.assertTrue(advance_booking_status(doc.name, "Quoted"))

	def test_advance_works_on_submitted_booking(self):
		"""booking_status is allow_on_submit — automation continues after submit."""
		doc = _insert(event_name="Test Submitted Advance", booking_status="Confirmed")
		doc.submit()
		self.assertEqual(doc.docstatus, 1)

		self.assertTrue(advance_booking_status(doc.name, "Paid"))
		self.assertEqual(_status(doc.name), "Paid")
		self.assertTrue(advance_booking_status(doc.name, "Executed"))
		self.assertEqual(_status(doc.name), "Executed")

	def test_submit_allowed_at_any_status(self):
		"""A booking can be submitted regardless of booking_status — the status
		is driven by linked documents (Quotation/SO/SI), not by the submit
		action itself. Same as Sales Order in ERPNext."""
		for status in ("New", "Quoted", "Invoiced", "Confirmed", "Paid"):
			doc = _insert(event_name=f"Submit at {status}", booking_status=status)
			doc.submit()
			self.assertEqual(doc.docstatus, 1)
			self.assertEqual(_status(doc.name), status)


@unittest.skipUnless(ERPNEXT_INSTALLED, "bookings require ERPNext (quotation-first flow)")
class TestHookWiring(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_quotation_link_hook_advances_to_quoted(self):
		doc = _insert(event_name="Test Qt Link", booking_status="New")
		on_quotation_update(
			SimpleNamespace(event_booking=doc.name, name="QTN-FAKE", doctype="Quotation"),
			None,
		)
		self.assertEqual(_status(doc.name), "Quoted")

	def test_quotation_submit_ensures_quoted_but_never_backwards(self):
		doc = _insert(event_name="Test Qt Submit", booking_status="New")
		on_quotation_submit(
			SimpleNamespace(event_booking=doc.name, name="QTN-FAKE", doctype="Quotation"),
			None,
		)
		self.assertEqual(_status(doc.name), "Quoted")

		# A booking already past Quoted is untouched by quotation submission
		doc2 = _insert(event_name="Test Qt Submit NoBack", booking_status="Invoiced")
		on_quotation_submit(
			SimpleNamespace(event_booking=doc2.name, name="QTN-FAKE2", doctype="Quotation"),
			None,
		)
		self.assertEqual(_status(doc2.name), "Invoiced")

	def test_si_submit_advances_to_invoiced(self):
		doc = _insert(event_name="Test SI Submit", booking_status="Quoted")
		on_sales_invoice_submit(
			SimpleNamespace(event_booking=doc.name, name="SINV-FAKE", doctype="Sales Invoice"),
			None,
		)
		self.assertEqual(_status(doc.name), "Invoiced")

	def test_si_partly_paid_advances_to_confirmed(self):
		doc = _insert(event_name="Test SI Partly Paid", booking_status="Invoiced")
		on_sales_invoice_update(
			SimpleNamespace(
				event_booking=doc.name, name="SINV-FAKE",
				doctype="Sales Invoice", docstatus=1, status="Partly Paid",
			),
			None,
		)
		self.assertEqual(_status(doc.name), "Confirmed")

	def test_si_fully_paid_advances_to_paid(self):
		doc = _insert(event_name="Test SI Fully Paid", booking_status="Confirmed")
		on_sales_invoice_update(
			SimpleNamespace(
				event_booking=doc.name, name="SINV-FAKE",
				doctype="Sales Invoice", docstatus=1, status="Paid",
			),
			None,
		)
		self.assertEqual(_status(doc.name), "Paid")

	def test_si_unpaid_does_not_advance(self):
		doc = _insert(event_name="Test SI Unpaid", booking_status="Invoiced")
		on_sales_invoice_update(
			SimpleNamespace(
				event_booking=doc.name, name="SINV-FAKE",
				doctype="Sales Invoice", docstatus=1, status="Unpaid",
			),
			None,
		)
		self.assertEqual(_status(doc.name), "Invoiced")

	def test_hooks_noop_without_link(self):
		on_quotation_submit(SimpleNamespace(event_booking=None, name="Q"), None)
		on_sales_invoice_update(
			SimpleNamespace(event_booking=None, name="S", docstatus=1, status="Paid"), None
		)
		on_sales_invoice_submit(
			SimpleNamespace(event_booking=None, name="S2"), None
		)


@unittest.skipUnless(ERPNEXT_INSTALLED, "real Quotation integration requires ERPNext")
class TestRealQuotationIntegration(FrappeTestCase):
	def setUp(self):
		ensure_test_customer_leaf_details()

	def tearDown(self):
		frappe.db.rollback()

	def _company(self):
		return frappe.db.get_value("Company", {}, "name", order_by="creation asc")

	def _make_quotation(self, booking):
		"""Build an insertable Quotation linked to *booking* with one item line.

		ERPNext's ``set_payment_schedule`` crashes on ``grand_total * ...`` when
		``grand_total`` is None (no items), so every test Quotation must carry
		at least one item row.
		"""
		item = get_or_create_test_item("Test Event Service Item")
		qt = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": booking.customer,
				"company": self._company(),
				"transaction_date": frappe.utils.today(),
				"event_booking": booking.name,
				"items": [
					{
						"item_code": item,
						"qty": 1,
						"rate": 100,
					}
				],
			}
		)
		qt.insert(ignore_permissions=True)
		return qt

	def test_draft_quotation_save_advances_booking(self):
		"""End-to-end: creating a linked draft Quotation fires the real
		doc_events hook → booking advances New → Quoted."""
		booking = _insert(event_name="Test E2E Qt", booking_status="New")
		qt = self._make_quotation(booking)

		self.assertEqual(frappe.db.get_value("Event Booking", booking.name, "quotation"), qt.name)
		self.assertEqual(_status(booking.name), "Quoted")

	def test_docstatus_cancel_cascades_to_linked_quotation(self):
		"""Cancelling a submitted booking synchronously cancels the linked
		submitted Quotation (before_cancel runs ahead of the back-link check)."""
		booking = _insert(event_name="Test E2E Cancel", booking_status="Confirmed")
		booking.submit()
		self.assertEqual(booking.docstatus, 1)

		qt = self._make_quotation(booking)
		qt.submit()
		self.assertEqual(qt.docstatus, 1)

		booking = frappe.get_doc("Event Booking", booking.name)
		booking.cancel()

		self.assertEqual(booking.docstatus, 2)
		self.assertEqual(frappe.db.get_value("Quotation", qt.name, "docstatus"), 2)


@unittest.skipUnless(ERPNEXT_INSTALLED, "bookings require ERPNext (quotation-first flow)")
class TestScheduler(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def _company(self):
		return frappe.db.get_value("Company", {}, "name", order_by="creation asc")

	def _make_quotation(self, booking):
		"""Build an insertable Quotation linked to *booking* with one item line."""
		item = get_or_create_test_item("Test Event Service Item")
		qt = frappe.get_doc(
			{
				"doctype": "Quotation",
				"quotation_to": "Customer",
				"party_name": booking.customer,
				"company": self._company(),
				"transaction_date": frappe.utils.today(),
				"event_booking": booking.name,
				"items": [{"item_code": item, "qty": 1, "rate": 100}],
			}
		)
		qt.insert(ignore_permissions=True)
		return qt

	def test_auto_execute_passed_events(self):
		past = frappe.utils.add_days(frappe.utils.today(), -3)

		confirmed = _insert(
			event_name="Test AutoExec Confirmed",
			booking_status="Confirmed", event_date=past,
		)
		paid = _insert(
			event_name="Test AutoExec Paid",
			booking_status="Paid", event_date=past,
		)
		invoiced = _insert(
			event_name="Test AutoExec Invoiced",
			booking_status="Invoiced", event_date=past,
		)
		executed = _insert(
			event_name="Test AutoExec Executed",
			booking_status="Executed", event_date=past,
		)
		future_confirmed = _insert(
			event_name="Test AutoExec Future",
			booking_status="Confirmed",
			event_date=frappe.utils.add_days(frappe.utils.today(), 3),
		)

		auto_execute_passed_events()

		self.assertEqual(_status(confirmed.name), "Executed")
		self.assertEqual(_status(paid.name), "Executed")
		# Only Confirmed / Paid bookings are auto-executed
		self.assertEqual(_status(invoiced.name), "Invoiced")
		self.assertEqual(_status(executed.name), "Executed")
		self.assertEqual(_status(future_confirmed.name), "Confirmed")

	def test_auto_execute_respects_toggle(self):
		past = frappe.utils.add_days(frappe.utils.today(), -3)
		doc = _insert(
			event_name="Test AutoExec Toggle",
			booking_status="Confirmed", event_date=past,
		)
		_set_toggle("auto_executed_after_event_date", 0)
		try:
			auto_execute_passed_events()
			self.assertEqual(_status(doc.name), "Confirmed")
		finally:
			_set_toggle("auto_executed_after_event_date", 1)
		auto_execute_passed_events()
		self.assertEqual(_status(doc.name), "Executed")

	def test_auto_execute_marks_linked_so_delivered(self):
		"""When a booking is auto-executed, its linked submitted Sales Order
		should be marked Fully Delivered (per_delivered = 100)."""
		from event_bookings.tests.fixtures import get_or_create_test_item

		past = frappe.utils.add_days(frappe.utils.today(), -3)
		booking = _insert(
			event_name="Test AutoExec SO Delivered",
			booking_status="Confirmed", event_date=past,
		)

		# Build a real Sales Order from the booking's quotation
		qt = self._make_quotation(booking)
		qt.submit()

		item = get_or_create_test_item("Test Event Service Item")
		so = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"customer": booking.customer,
				"company": qt.company,
				"transaction_date": frappe.utils.add_days(frappe.utils.today(), -5),
				"delivery_date": past,
				"items": [{"item_code": item, "qty": 1, "rate": 100}],
			}
		).insert(ignore_permissions=True)
		so.submit()
		frappe.db.set_value("Event Booking", booking.name, "sales_order", so.name)

		auto_execute_passed_events()

		self.assertEqual(_status(booking.name), "Executed")
		self.assertEqual(
			frappe.db.get_value("Sales Order", so.name, "delivery_status"),
			"Fully Delivered",
		)
		self.assertEqual(
			float(frappe.db.get_value("Sales Order", so.name, "per_delivered")),
			100.0,
		)


@unittest.skipUnless(ERPNEXT_INSTALLED, "bookings require ERPNext (quotation-first flow)")
class TestLegacyUpgradeRegression(FrappeTestCase):
	"""P1-19 — bookings in every pre-upgrade status survive the automation
	unchanged, except the intended matrix transitions."""

	def tearDown(self):
		frappe.db.rollback()

	def test_legacy_bookings_only_change_per_matrix(self):
		past = frappe.utils.add_days(frappe.utils.today(), -10)
		future = frappe.utils.add_days(frappe.utils.today(), 10)

		# Seed one booking in every pre-upgrade status (same option values,
		# new order) with legacy link + totals, all past-dated, all draft.
		seed = []  # (original_status, name)
		for status in STATUS_ORDER + [CANCELLED]:
			doc = _insert(
				event_name=f"Legacy {status}",
				booking_status=status,
				event_date=past,
				guest_count=50,
			)
			frappe.db.set_value("Event Booking", doc.name, "quotation", "QTN-LEGACY")
			frappe.db.set_value(
				"Event Booking", doc.name,
				{"total_estimated": 1000.0, "total_actual": 0.0},
			)
			seed.append((status, doc.name))

		future_doc = _insert(
			event_name="Legacy Future Confirmed",
			booking_status="Confirmed", event_date=future,
		)

		# The daily automation exactly as it runs after the upgrade.
		auto_execute_passed_events()

		expected = {
			"New": "New",
			"Quoted": "Quoted",
			"Invoiced": "Invoiced",
			"Confirmed": "Executed",       # intended matrix transition
			"Paid": "Executed",            # intended matrix transition
			"Executed": "Executed",
			CANCELLED: CANCELLED,
		}
		for original, name in seed:
			self.assertEqual(_status(name), expected[original], name)
			row = frappe.db.get_value(
				"Event Booking", name,
				["docstatus", "quotation", "total_estimated", "total_actual"],
				as_dict=True,
			)
			# Legacy data integrity — nothing touched except booking_status
			self.assertEqual(row.docstatus, 0)
			self.assertEqual(row.quotation, "QTN-LEGACY")
			self.assertEqual(float(row.total_estimated), 1000.0)
			self.assertEqual(float(row.total_actual), 0.0)

		# Future-dated Confirmed booking untouched
		self.assertEqual(_status(future_doc.name), "Confirmed")

	def test_status_order_matches_doctype_options(self):
		"""The shipped Select options must be exactly STATUS_ORDER + Cancelled."""
		meta = frappe.get_meta("Event Booking")
		options = meta.get_options("booking_status").split("\n")
		self.assertEqual(options, STATUS_ORDER + [CANCELLED])


@unittest.skipUnless(ERPNEXT_INSTALLED, "bookings require ERPNext (quotation-first flow)")
class TestLifecycleDateStamping(FrappeTestCase):
	"""confirmed_on / cancelled_on replace `modified` as the analytics date basis.

	`modified` is the last edit of *anything* on the booking, so an unrelated
	edit silently re-dated a historical conversion or loss into the current
	period. These fields are written once and never moved.
	"""

	def tearDown(self):
		frappe.db.rollback()

	def test_not_stamped_before_confirmed(self):
		doc = _insert(event_name="Stamp New", booking_status="New")
		self.assertIsNone(doc.confirmed_on)
		self.assertIsNone(doc.cancelled_on)

	def test_confirmed_on_stamped_when_skipping_confirmed(self):
		"""A booking can jump Invoiced -> Paid and never pass through Confirmed."""
		doc = _insert(event_name="Stamp Skip", booking_status="Invoiced")
		self.assertIsNone(doc.confirmed_on)

		doc.booking_status = "Paid"
		doc.save(ignore_permissions=True)
		self.assertIsNotNone(doc.confirmed_on)
		self.assertEqual(frappe.utils.getdate(doc.confirmed_on), frappe.utils.getdate(frappe.utils.today()))

	def test_confirmed_on_never_moves(self):
		doc = _insert(event_name="Stamp Once", booking_status="Confirmed")
		first = doc.confirmed_on
		self.assertIsNotNone(first)

		frappe.db.set_value("Event Booking", doc.name, "confirmed_on", "2020-01-01")
		doc.reload()
		doc.booking_status = "Executed"
		doc.save(ignore_permissions=True)

		self.assertEqual(frappe.utils.getdate(doc.confirmed_on), frappe.utils.getdate("2020-01-01"))

	def test_cancelled_on_stamped_on_cancel(self):
		doc = _insert(event_name="Stamp Cancel", booking_status="Confirmed")
		self.assertIsNone(doc.cancelled_on)

		doc.booking_status = CANCELLED
		doc.save(ignore_permissions=True)
		self.assertIsNotNone(doc.cancelled_on)
		self.assertEqual(frappe.utils.getdate(doc.cancelled_on), frappe.utils.getdate(frappe.utils.today()))

	def test_automated_advance_stamps_confirmed_on(self):
		"""advance_booking_status writes via db.set_value, bypassing the document
		lifecycle — it must stamp confirmed_on itself."""
		doc = _insert(event_name="Stamp Auto", booking_status="Invoiced")
		self.assertTrue(advance_booking_status(doc.name, "Confirmed", reason="test"))

		stamped = frappe.db.get_value("Event Booking", doc.name, "confirmed_on")
		self.assertIsNotNone(stamped)
		self.assertEqual(frappe.utils.getdate(stamped), frappe.utils.getdate(frappe.utils.today()))

	def test_cancelling_a_booking_does_not_raise(self):
		"""Regression: cancel_linked_documents used frappe.in_test, a v16-only
		API, so every cancellation raised AttributeError on v15."""
		doc = _insert(event_name="Cancel No Raise", booking_status="Confirmed")
		doc.booking_status = CANCELLED
		doc.save(ignore_permissions=True)
		self.assertEqual(_status(doc.name), CANCELLED)


@unittest.skipUnless(ERPNEXT_INSTALLED, "bookings require ERPNext (quotation-first flow)")
class TestSubmittedBookingLifecycle(FrappeTestCase):
	"""Bookings are submitted (docstatus 1) in normal use.

	booking_status is allow_on_submit, so it keeps changing after submit — but
	the lifecycle date fields were not, so every stamp on a submitted booking
	was silently discarded and D-4 was inert in production.
	"""

	def tearDown(self):
		frappe.db.rollback()

	def test_confirmed_on_stamped_after_submit(self):
		doc = _insert(event_name="Submitted Stamp", booking_status="New")
		doc.submit()
		self.assertIsNone(doc.confirmed_on)

		doc.booking_status = "Confirmed"
		doc.save(ignore_permissions=True)
		doc.reload()

		self.assertIsNotNone(doc.confirmed_on)
		self.assertEqual(
			frappe.utils.getdate(doc.confirmed_on), frappe.utils.getdate(frappe.utils.today())
		)

	def test_docstatus_cancel_syncs_booking_status(self):
		"""ERPNext derives status from docstatus (status_updater.py:
		["Cancelled", "eval:self.docstatus==2"]). A docstatus-cancelled booking
		must not keep reading as Confirmed, or it counts as converted forever."""
		doc = _insert(event_name="Docstatus Cancel", booking_status="New")
		doc.submit()
		doc.cancel()
		doc.reload()

		self.assertEqual(doc.docstatus, 2)
		self.assertEqual(doc.booking_status, CANCELLED)
		self.assertIsNotNone(doc.cancelled_on)
		self.assertEqual(
			frappe.utils.getdate(doc.cancelled_on), frappe.utils.getdate(frappe.utils.today())
		)

	def test_reports_exclude_cancelled_bookings(self):
		"""Cancelled bookings never appear in a report, matching ERPNext, where
		every report pins docstatus = 1."""
		from event_bookings.event_bookings.report.event_booking_pipeline import (
			event_booking_pipeline,
		)
		from event_bookings.event_bookings.report.event_booking_profitability import (
			event_booking_profitability,
		)

		live = _insert(event_name="Report Visible", booking_status="Confirmed")
		gone = _insert(event_name="Report Cancelled", booking_status=CANCELLED)

		for module in (event_booking_pipeline, event_booking_profitability):
			names = {row["event_name"] for row in module.get_data({})}
			self.assertIn(live.name, names, module.__name__)
			self.assertNotIn(gone.name, names, module.__name__)

	def test_cancelled_status_filter_cannot_resurface_them(self):
		"""Even if 'Cancelled' is passed explicitly, the exclusion holds."""
		from event_bookings.event_bookings.report.event_booking_pipeline import (
			event_booking_pipeline,
		)

		cancelled = _insert(event_name="Filter Probe", booking_status=CANCELLED)
		rows = event_booking_pipeline.get_data({"booking_status": CANCELLED})
		self.assertNotIn(cancelled.name, {row["event_name"] for row in rows})


@unittest.skipUnless(ERPNEXT_INSTALLED, "bookings require ERPNext (quotation-first flow)")
class TestSubmittedHookDispatch(FrappeTestCase):
	"""Frappe dispatches a different hook chain once a document is submitted.

	run_before_save_methods runs only before_update_after_submit (not validate /
	before_save) and run_post_save_methods runs only on_update_after_submit (not
	on_update). booking_status is allow_on_submit, so everything hanging off the
	save chain silently stopped working on submitted bookings.
	"""

	def tearDown(self):
		frappe.db.rollback()

	def test_status_cancel_cascades_on_submitted_booking(self):
		"""The linked Quotation / Sales Order / Sales Invoice cascade must still
		fire when a *submitted* booking is cancelled by status."""
		doc = _insert(event_name="Submitted Cascade", booking_status="Confirmed")
		doc.submit()

		target = (
			"event_bookings.event_bookings.doctype.event_booking"
			".event_booking._cancel_linked_documents"
		)
		with patch(target) as cascade:
			doc.booking_status = CANCELLED
			doc.save(ignore_permissions=True)

		cascade.assert_called_once_with(doc.name)

	def test_staffing_alert_fires_on_submitted_booking(self):
		doc = _insert(event_name="Submitted Staffing", booking_status="New")
		doc.submit()

		with patch.object(type(doc), "_notify_staff_requirements") as notify:
			doc.booking_status = "Confirmed"
			doc.save(ignore_permissions=True)

		notify.assert_called_once()

	def test_calendar_sync_registered_for_post_submit_updates(self):
		"""on_update does not fire after submit, so the calendar entry would
		freeze at the status the booking had when it was submitted."""
		events = frappe.get_hooks("doc_events").get("Event Booking", {})
		self.assertIn("on_update_after_submit", events)
		self.assertIn(
			"event_bookings.utils.google_calendar_sync.push_to_google_calendar",
			events["on_update_after_submit"],
		)


class TestChartCompanyScoping(FrappeTestCase):
	"""Company is the only separator between event deals and other business, so
	the pipeline reports must never fall back to aggregating every company."""

	def test_company_falls_back_to_default_company(self):
		from event_bookings.event_bookings.report.event_inquiry_vs_conversion.event_inquiry_vs_conversion import (
			validate_filters,
		)

		default = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
			"Global Defaults", "default_company"
		)
		if not default:
			self.skipTest("site has no default company")

		filters = frappe._dict({})
		validate_filters(filters)
		self.assertEqual(filters.get("company"), default)

	def test_explicit_company_wins(self):
		from event_bookings.event_bookings.report.event_lead_conversion_funnel.event_lead_conversion_funnel import (
			validate_filters,
		)

		filters = frappe._dict({"company": "Some Other Co"})
		validate_filters(filters)
		self.assertEqual(filters.get("company"), "Some Other Co")


@unittest.skipUnless(ERPNEXT_INSTALLED, "requires ERPNext Sales Invoice")
class TestRealPaymentPathIntegration(FrappeTestCase):
	"""The settle-an-invoice path, driven against real ERPNext documents.

	Every other test in this file drives the hooks with a SimpleNamespace
	carrying a pre-set ``status``. That fake bypasses the only code the
	production payment route actually executes — which is how
	``si.set_status(update_status=True)`` shipped and raised TypeError on every
	call for the life of the feature, swallowed by the hook's own except block
	while the suite stayed green.

	These tests call the real functions against a real submitted invoice, so a
	signature drift in ERPNext fails here instead of silently disabling the
	Confirmed/Paid lifecycle in production.
	"""

	def setUp(self):
		ensure_test_customer_leaf_details()

	def tearDown(self):
		frappe.db.rollback()

	def _company(self):
		return frappe.db.get_value("Company", {}, "name", order_by="creation asc")

	def _make_submitted_invoice(self, booking):
		item = get_or_create_test_item("Test Event Service Item")
		si = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": booking.customer,
			"company": self._company(),
			"posting_date": frappe.utils.today(),
			"due_date": frappe.utils.today(),
			"event_booking": booking.name,
			"items": [{"item_code": item, "qty": 1, "rate": 100}],
		})
		si.insert(ignore_permissions=True)
		si.submit()
		return si

	def test_advance_from_sales_invoice_does_not_raise(self):
		"""Guards the TypeError that silently killed the whole payment path."""
		booking = _insert(event_name="Real SI Payment Path", booking_status="Invoiced")
		si = self._make_submitted_invoice(booking)

		# Called directly, outside on_payment_entry_submit's except block, so a
		# failure surfaces instead of being logged and discarded.
		_eb_advance_from_sales_invoice("PE-TEST", si.name)

		self.assertIn(_status(booking.name), ("Invoiced", "Confirmed", "Paid"))

	def test_settled_invoice_advances_booking_to_paid(self):
		"""An invoice with nothing outstanding must carry the booking to Paid."""
		booking = _insert(event_name="Real SI Settled", booking_status="Invoiced")
		si = self._make_submitted_invoice(booking)

		# Settle it the way a payment would, then let the hook re-read status.
		si.db_set("outstanding_amount", 0, update_modified=False)
		_eb_advance_from_sales_invoice("PE-TEST", si.name)

		self.assertEqual(_status(booking.name), "Paid")

	def test_cash_invoice_reaches_paid_without_a_payment_entry(self):
		"""is_paid invoices create no Payment Entry, so on_submit must cover them."""
		booking = _insert(event_name="Real SI Cash", booking_status="Quoted")
		si = self._make_submitted_invoice(booking)
		si.db_set("outstanding_amount", 0, update_modified=False)
		si.set_status(update=True, update_modified=False)

		on_sales_invoice_submit(frappe.get_doc("Sales Invoice", si.name), None)

		self.assertEqual(_status(booking.name), "Paid")
