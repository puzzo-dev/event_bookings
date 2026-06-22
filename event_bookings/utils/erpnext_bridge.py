"""ERPNext / HRMS integration bridge.

All ERPNext- and HRMS-specific functionality is isolated here.
Every function in this module is safe to call regardless of whether
those apps are installed — callers never need to guard imports themselves.

Design contract
---------------
- When ERPNext IS installed  → full integration path is used.
- When ERPNext is NOT installed → graceful fallback or clear user-facing
  error (never an unhandled ImportError / AttributeError).
- The core event_bookings app has zero top-level imports from erpnext or hrms.
"""

import frappe
from frappe import _


# ── Availability helpers ────────────────────────────────────────────────


def is_erpnext_installed() -> bool:
	"""Return True if ERPNext is installed on the current site."""
	return "erpnext" in frappe.get_installed_apps()


def is_hrms_installed() -> bool:
	"""Return True if HRMS is installed on the current site."""
	return "hrms" in frappe.get_installed_apps()


# ── Fiscal Year ─────────────────────────────────────────────────────────


def get_fiscal_year_safe(date=None) -> str:
	"""Return the fiscal year name for *date* (defaults to today).

	Unlike erpnext.accounts.utils.get_fiscal_year this function:
	  • Never monkey-patches anything.
	  • Never makes a synchronous AJAX call.
	  • Never raises FiscalYearError — returns "" when no FY exists.

	Resolution order
	----------------
	1. ERPNext's get_fiscal_years() if ERPNext is installed.
	2. Direct SQL query on tabFiscal Year as fallback.
	3. Most-recent active FY regardless of date as last resort.
	4. Empty string — no fiscal year exists at all.
	"""
	if date is None:
		date = frappe.utils.nowdate()

	if not is_erpnext_installed():
		return ""

	# Preferred: use ERPNext's official utility (handles company-scoped FYs)
	try:
		from erpnext.accounts.utils import get_fiscal_years, FiscalYearError

		result = get_fiscal_years(date, as_dict=False)
		if result:
			return result[0][0]
	except Exception:
		pass  # fall through to direct query

	# Direct query fallback — most recent FY that contains date
	if not frappe.db.table_exists("Fiscal Year"):
		return ""

	row = frappe.db.sql(
		"""
		SELECT name
		FROM `tabFiscal Year`
		WHERE disabled = 0
		  AND year_start_date <= %(date)s
		  AND year_end_date   >= %(date)s
		ORDER BY year_start_date DESC
		LIMIT 1
		""",
		{"date": date},
	)
	if row:
		return row[0][0]

	# Last resort: most recent active FY regardless of date range
	return (
		frappe.db.get_value(
			"Fiscal Year",
			{"disabled": 0},
			"name",
			order_by="year_start_date desc",
		)
		or ""
	)


def get_fiscal_year_dates_safe(fiscal_year_name: str):
	"""Return ``(start_date, end_date)`` for a fiscal year name.

	Resolution order
	----------------
	1. ERPNext's get_fiscal_year(fiscal_year=...) if available.
	2. Direct SQL on tabFiscal Year as fallback.
	3. ``(None, None)`` — fiscal year not found or ERPNext not installed.
	"""
	if not fiscal_year_name:
		return None, None

	if is_erpnext_installed():
		try:
			from erpnext.accounts.utils import get_fiscal_year

			result = get_fiscal_year(fiscal_year=fiscal_year_name)
			if result:
				return result[1], result[2]
		except Exception:
			pass

	if not frappe.db.table_exists("Fiscal Year"):
		return None, None

	row = frappe.db.get_value(
		"Fiscal Year",
		{"name": fiscal_year_name, "disabled": 0},
		["year_start_date", "year_end_date"],
		as_dict=True,
	)
	if row:
		return row.year_start_date, row.year_end_date
	return None, None


# ── Lead → Customer conversion ──────────────────────────────────────────


def make_customer_from_lead(lead_name: str):
	"""Create and return an **unsaved** Customer document from a Lead.

	Resolution order
	----------------
	1. ERPNext's erpnext.crm.doctype.lead.lead.make_customer — the canonical
	   path; preserves all CRM metadata.
	2. Direct build from Lead fields — used when ERPNext is not installed or
	   when make_customer is unavailable (API change protection).

	Mandatory ERPNext defaults (customer_group, territory) are always
	populated so the returned document can be inserted without further
	intervention.

	Caller is responsible for calling .insert() on the returned document.
	"""
	if not frappe.db.exists("DocType", "Customer"):
		frappe.throw(
			_("Customer management is not available. ERPNext must be installed to convert a Lead to a Customer.")
		)

	# Preferred: delegate to ERPNext's official CRM converter
	if is_erpnext_installed():
		try:
			from erpnext.crm.doctype.lead.lead import make_customer

			customer_doc = make_customer(lead_name)
		except (ImportError, AttributeError):
			# ERPNext API changed — degrade gracefully
			customer_doc = _build_customer_from_lead_fields(lead_name)
	else:
		customer_doc = _build_customer_from_lead_fields(lead_name)

	# Ensure ERPNext mandatory fields always have safe defaults
	if not getattr(customer_doc, "customer_group", None):
		customer_doc.customer_group = (
			frappe.db.get_default("customer_group")
			or frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
			or "All Customer Groups"
		)

	if not getattr(customer_doc, "territory", None):
		customer_doc.territory = (
			frappe.db.get_default("territory")
			or frappe.db.get_value("Territory", {"is_group": 0}, "name")
			or "All Territories"
		)

	return customer_doc


def _build_customer_from_lead_fields(lead_name: str):
	"""Build a Customer document directly from Lead fields (no ERPNext helpers)."""
	lead = frappe.get_doc("Lead", lead_name)
	customer_doc = frappe.new_doc("Customer")
	customer_doc.customer_name = (
		lead.company_name
		or getattr(lead, "lead_name", None)
		or getattr(lead, "first_name", None)
		or lead_name
	)
	customer_doc.lead_name = lead_name
	customer_doc.customer_type = "Company" if lead.company_name else "Individual"
	return customer_doc
