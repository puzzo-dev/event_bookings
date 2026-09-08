"""D-10 regression tests for the ERPNext-native dashboard layer.

Covers:
- Module-folder sync: every chart / card / dashboard link / report that the
  app ships in ``dashboard_chart/``, ``number_card/`` and
  ``event_bookings_dashboard/`` exists on the site as a standard record,
  and zero custom Dashboard Chart Sources remain.
- Number Card filters reference real fields on their target doctype
  (guards against another ``event_timing``-class bug).
- Report charts count correctly: each report's totals are compared against
  the same aggregation done directly against the database, so the test
  holds on any site data (fresh install or long-lived production copy):
  ``Event Inquiry vs Conversion``, ``Event Lead Conversion Funnel`` and
  ``Event Booking Trends`` (Cancelled exclusion, actual-fallback-estimated,
  group-by Event Type).
"""

import json
import os
import unittest

import frappe
from frappe.utils import cint
from event_bookings.tests.compat import FrappeTestCase

from event_bookings.tests.fixtures import (
	ensure_test_customer_leaf_details,
	get_or_create_test_customer,
	get_or_create_test_event_type,
	get_or_create_test_item,
)

ERPNEXT_INSTALLED = "erpnext" in frappe.get_installed_apps()

CHARTS = {
	"Event Booking Revenue Trends": "Report",
	"Event Booking Count Trends": "Report",
	"Event Revenue Trend by Event Type": "Report",
	"Events By Event Type": "Report",
	"Event Inquiry vs Conversion": "Report",
	"Event Lead Conversion Funnel": "Report",
	"Monthly Events": "Count",
	"Event Deals Completed": "Sum",
	"Event Deals Lost": "Sum",
}

CARDS = [
	"Upcoming Events",
	"Events This Month",
	"Pending Invoices",
	"Total Revenue",
	"Deals Completed",
	"Deals Pending",
	"Deals Lost",
	"New Inquiries",
	"Leads Booked",
]


def _shipped(doctype_folder, name):
	"""The record as this branch ships it, read from the module folder."""
	path = os.path.join(
		frappe.get_app_path("event_bookings", "event_bookings", doctype_folder),
		frappe.scrub(name),
		f"{frappe.scrub(name)}.json",
	)
	with open(path) as f:
		return json.load(f)


class TestModuleFolderSync(FrappeTestCase):
	"""sync_dashboards must materialise every shipped record, as shipped."""

	def test_all_charts_cards_dashboard_and_reports_exist(self):
		frappe.utils.dashboard.sync_dashboards("event_bookings")

		# is_standard is compared against the module folder rather than
		# hardcoded to 1: the production branches ship these records with
		# is_standard 0 so the app installs without developer_mode, and the
		# development branches ship 1. Pinning the assertion to one of those
		# made the suite fail on the other branch for a difference that is
		# deliberate. What must hold on every branch is that the database
		# matches what the branch ships — which is also the real bug this
		# catches, a record that failed to sync from its folder.
		for chart_name, chart_type in CHARTS.items():
			chart = frappe.get_doc("Dashboard Chart", chart_name)
			self.assertEqual(chart.chart_type, chart_type, chart_name)
			self.assertEqual(
				chart.is_standard,
				cint(_shipped("dashboard_chart", chart_name).get("is_standard")),
				chart_name,
			)
			if chart_type == "Report":
				self.assertTrue(chart.report_name, chart_name)
				self.assertTrue(
					frappe.db.exists("Report", chart.report_name), chart.report_name
				)

		for card in CARDS:
			self.assertEqual(
				cint(frappe.db.get_value("Number Card", card, "is_standard")),
				cint(_shipped("number_card", card).get("is_standard")),
				card,
			)

		dashboard = frappe.get_doc("Dashboard", "Event Bookings")
		self.assertEqual(len(dashboard.charts), len(CHARTS))
		self.assertEqual(len(dashboard.cards), len(CARDS))

	def test_no_custom_chart_sources_remain(self):
		self.assertEqual(
			frappe.db.count("Dashboard Chart Source", {"module": "Event Bookings"}), 0
		)

	def test_number_card_filters_reference_real_fields(self):
		"""Every field in every card's filters must exist on its doctype —
		the class of bug where ``Events This Month`` filtered on a
		non-existent ``event_timing`` field and silently broke to 0."""
		for card_name in CARDS:
			card = frappe.get_doc("Number Card", card_name)
			self.assertTrue(card.document_type, card_name)
			meta = frappe.get_meta(card.document_type)
			for flt in frappe.parse_json(card.filters_json) or []:
				fieldname = flt[1] if isinstance(flt, (list, tuple)) and len(flt) > 1 else None
				if fieldname in ("docstatus", "name"):
					continue
				self.assertTrue(
					meta.has_field(fieldname),
					f"{card_name} filters on missing field {card_name}.{fieldname}",
				)


def _company():
	return frappe.db.get_value("Company", {}, "name", order_by="creation asc")


def _get_or_create_test_lead(lead_name="Test Funnel Lead"):
	# Leads are named by naming series, so look up by lead_name and return
	# the document's actual name (what Quotation.party_name must hold).
	existing = frappe.db.get_value("Lead", {"lead_name": lead_name}, "name")
	if existing:
		return existing
	return frappe.get_doc({"doctype": "Lead", "lead_name": lead_name}).insert(
		ignore_permissions=True
	).name


def _make_quotation(party_name, quotation_to="Customer", status=None, submit=True):
	item = get_or_create_test_item("Test Event Service Item")
	qt = frappe.get_doc(
		{
			"doctype": "Quotation",
			"quotation_to": quotation_to,
			"party_name": party_name,
			"company": _company(),
			"transaction_date": frappe.utils.today(),
			"items": [{"item_code": item, "qty": 1, "rate": 100}],
		}
	).insert(ignore_permissions=True)
	if submit:
		qt.submit()
	if status:
		frappe.db.set_value("Quotation", qt.name, "status", status, update_modified=False)
	return qt


def _dataset_totals(chart):
	return {d["name"]: sum(d["values"]) for d in chart["data"]["datasets"]}


@unittest.skipUnless(ERPNEXT_INSTALLED, "report charts require ERPNext doctypes")
class TestEventInquiryVsConversion(FrappeTestCase):
	def setUp(self):
		ensure_test_customer_leaf_details()
		self.customer = get_or_create_test_customer()

	def tearDown(self):
		frappe.db.rollback()

	def test_totals_match_database(self):
		# Seed one won and one lost deal; draft stays invisible.
		_make_quotation(self.customer, status="Ordered")
		_make_quotation(self.customer, status="Lost")
		_make_quotation(self.customer, submit=False)

		from event_bookings.event_bookings.report.event_inquiry_vs_conversion.event_inquiry_vs_conversion import (
			execute,
		)

		filters = {"company": _company(), "period": "Monthly"}
		columns, data, _, chart, _, _ = execute(filters)
		totals = {row["metric"]: row["total"] for row in data}

		expected = frappe.db.count(
			"Quotation", {"docstatus": 1, "company": _company()}
		)
		expected_won = frappe.db.count(
			"Quotation", {"docstatus": 1, "company": _company(), "status": "Ordered"}
		)
		expected_lost = frappe.db.count(
			"Quotation",
			{"docstatus": 1, "company": _company(), "status": ("in", ["Lost", "Expired"])},
		)

		self.assertEqual(totals["Inquiries"], expected)
		self.assertEqual(totals["Won"], expected_won)
		self.assertEqual(totals["Lost"], expected_lost)
		# Draft quotation never counted
		self.assertGreaterEqual(totals["Inquiries"], 2)
		self.assertEqual(_dataset_totals(chart), totals)


@unittest.skipUnless(ERPNEXT_INSTALLED, "report charts require ERPNext doctypes")
class TestEventLeadConversionFunnel(FrappeTestCase):
	def setUp(self):
		ensure_test_customer_leaf_details()
		self.customer = get_or_create_test_customer()
		self.event_type = get_or_create_test_event_type()
		self.item = get_or_create_test_item("Test Event Service Item")

	def tearDown(self):
		frappe.db.rollback()

	def test_stage_totals_match_database(self):
		# A lead-sourced submitted quotation with a booking and a linked SO.
		lead = _get_or_create_test_lead()
		qt = _make_quotation(lead, quotation_to="Lead", status="Ordered")
		booking = frappe.get_doc(
			{
				"doctype": "Event Booking",
				"event_name": "Funnel Regression Booking",
				"event_type": self.event_type,
				"booking_status": "Confirmed",
				"booking_date": frappe.utils.today(),
				"event_date": frappe.utils.add_days(frappe.utils.today(), 30),
				"event_time": "18:00:00",
				"event_location": "Test Hall",
				"customer": self.customer,
				"company": _company(),
				"quotation": qt.name,
			}
		).insert(ignore_permissions=True)

		so = frappe.get_doc(
			{
				"doctype": "Sales Order",
				"customer": self.customer,
				"company": _company(),
				"transaction_date": frappe.utils.today(),
				"delivery_date": frappe.utils.add_days(frappe.utils.today(), 30),
				"items": [{"item_code": self.item, "qty": 1, "rate": 100}],
				"event_booking": booking.name,
			}
		).insert(ignore_permissions=True)
		so.submit()

		from event_bookings.event_bookings.report.event_lead_conversion_funnel.event_lead_conversion_funnel import (
			execute,
		)

		company = _company()
		columns, data, _, chart, _, _ = execute({"company": company, "period": "Monthly"})
		totals = {row["metric"]: row["total"] for row in data}

		def count(doctype, extra=None):
			filters = {"docstatus": 1, "company": company}
			filters.update(extra or {})
			return frappe.db.count(doctype, filters)

		self.assertEqual(totals["Leads Quoted"], count("Quotation", {"quotation_to": "Lead"}))
		self.assertEqual(totals["Quotations Issued"], count("Quotation"))
		self.assertEqual(
			totals["Orders Confirmed"],
			frappe.db.count(
				"Sales Order",
				{
					"docstatus": 1,
					"company": company,
					"event_booking": ("is", "set"),
				},
			),
		)
		self.assertEqual(
			totals["Invoiced"],
			frappe.db.count(
				"Sales Invoice",
				{
					"docstatus": 1,
					"company": company,
					"event_booking": ("is", "set"),
				},
			),
		)
		self.assertGreaterEqual(totals["Orders Confirmed"], 1)
		self.assertEqual(_dataset_totals(chart), totals)


@unittest.skipUnless(ERPNEXT_INSTALLED, "report charts require ERPNext doctypes")
class TestEventBookingTrends(FrappeTestCase):
	def setUp(self):
		ensure_test_customer_leaf_details()
		self.customer = get_or_create_test_customer()
		self.event_type = get_or_create_test_event_type()

	def tearDown(self):
		frappe.db.rollback()

	def _insert(self, event_name, status, total_actual=0, total_estimated=0):
		# Insertion runs validate -> calculate_totals, which recomputes both
		# totals from linked documents (0 for a fresh seed). Totals are the
		# automation hooks' domain — set them the same way the hooks do.
		booking = frappe.get_doc(
			{
				"doctype": "Event Booking",
				"event_name": event_name,
				"event_type": self.event_type,
				"booking_status": status,
				"booking_date": frappe.utils.today(),
				"event_date": frappe.utils.add_days(frappe.utils.today(), 30),
				"event_time": "18:00:00",
				"event_location": "Test Hall",
				"customer": self.customer,
				"company": _company(),
			}
		).insert(ignore_permissions=True)
		values = {}
		if total_actual:
			values["total_actual"] = total_actual
		if total_estimated:
			values["total_estimated"] = total_estimated
		if values:
			frappe.db.set_value(
				"Event Booking", booking.name, values, update_modified=False
			)
		return booking

	def test_revenue_excludes_cancelled_and_falls_back_to_estimated(self):
		self._insert("Trends Actual", "Confirmed", total_actual=1000)
		self._insert("Trends Estimated Only", "Quoted", total_estimated=500)
		self._insert("Trends Cancelled", "Cancelled", total_actual=9999)

		from event_bookings.event_bookings.report.event_booking_trends.event_booking_trends import (
			execute,
		)

		company = _company()
		columns, data, _, chart, _, _ = execute(
			{
				"company": company,
				"period": "Monthly",
				"based_on": "Revenue",
				"date_field": "booking_date",
			}
		)
		reported = data[0]["total"]

		expected = frappe.db.sql(
			"""
			SELECT SUM(IF(IFNULL(total_actual, 0) > 0, total_actual, IFNULL(total_estimated, 0)))
			FROM `tabEvent Booking`
			WHERE docstatus < 2 AND booking_status != 'Cancelled' AND company = %s
			""",
			company,
		)[0][0] or 0

		self.assertEqual(reported, expected)
		self.assertGreaterEqual(reported, 1500)  # actual + fallback, cancelled excluded
		self.assertNotEqual(reported, 9999 + expected)

	def test_group_by_event_type_emits_one_dataset_per_type(self):
		self._insert("Grouped A", "Confirmed", total_actual=300)

		from event_bookings.event_bookings.report.event_booking_trends.event_booking_trends import (
			execute,
		)

		columns, data, _, chart, _, _ = execute(
			{
				"company": _company(),
				"period": "Monthly",
				"based_on": "Revenue",
				"date_field": "event_date",
				"group_by": "Event Type",
			}
		)
		datasets = _dataset_totals(chart)
		self.assertIn(self.event_type, datasets)
		self.assertGreaterEqual(datasets[self.event_type], 300)
