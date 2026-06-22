import frappe
from frappe.utils import cstr

from event_bookings.utils.erpnext_bridge import get_fiscal_year_safe, is_erpnext_installed, is_hrms_installed
from event_bookings.utils.seed import seed_event_types


def after_install():
	"""
	Hook executed after app is installed.
	- Seeds default Event Types
	- Creates event-specific Chart of Accounts accounts
	- Creates default Email Templates
	- Registers Event Booking as an Accounting Dimension
	- Creates custom fields on native doctypes
	"""
	seed_event_types()
	create_email_templates()
	if is_erpnext_installed():
		create_event_coa_accounts()    # requires Account + Company DocTypes
		create_accounting_dimension()  # auto-creates system custom fields on SO, SI, SE, PI, EC
		create_custom_fields()         # creates remaining app custom fields
		create_default_settings()      # one Event Booking Settings record per company
	upgrade_designation_for_hrms()  # Link(Designation) when HRMS present, Data otherwise
	migrate_workspace_charts()     # ensure workspace references current charts


def after_migrate():
	"""
	Hook executed after every bench migrate.
	Cleans up any legacy is_standard charts that fixtures cannot delete,
	ensures the workspace content block always references the current charts,
	and creates missing Event Booking Settings records for companies added after install.
	"""
	migrate_workspace_charts()
	if is_erpnext_installed():
		create_default_settings()
	upgrade_designation_for_hrms()  # re-apply on every migrate — JSON resets it to Data


def migrate_workspace_charts():
	"""
	Idempotent: ensure the workspace content references the correct Report-based charts
	and that all Dashboard Chart records have valid filters_json.
	"""
	import json

	# ── 1. Fix stale filters_json in Dashboard Chart records ──────────────
	_fix_chart_filters_json()

	# ── 2. Sync workspace content and charts child table ──────────────────
	if not frappe.db.exists("Workspace", "Event Bookings"):
		return

	ws = frappe.get_doc("Workspace", "Event Bookings")

	try:
		content = json.loads(ws.content or "[]")
	except (ValueError, TypeError):
		content = []

	# Replace any legacy chart references in the content blocks
	chart_map = {
		"Event Revenue Trend": "Event Booking Revenue Trends",
		"Monthly Events":      "Event Booking Count Trends",
	}

	updated = False
	for block in content:
		if block.get("type") == "chart":
			old_name = block.get("data", {}).get("chart_name")
			if old_name in chart_map:
				block["data"]["chart_name"] = chart_map[old_name]
				updated = True

	# Ensure onboarding block at position 0
	if not any(b.get("type") == "onboarding" for b in content):
		content.insert(0, {
			"id": "onboard01",
			"type": "onboarding",
			"data": {"onboarding_name": "Event Bookings Onboarding", "col": 12},
		})
		updated = True

	# Ensure all three charts are in the content blocks
	current_chart_blocks = {
		b["data"]["chart_name"]
		for b in content
		if b.get("type") == "chart"
	}
	desired_charts = [
		("Event Booking Revenue Trends", 6),
		("Event Booking Count Trends",   6),
		("Events By Event Type",         6),
	]
	for chart_name, col in desired_charts:
		if chart_name not in current_chart_blocks:
			content.append({
				"type": "chart",
				"data": {"chart_name": chart_name, "col": col},
			})
			updated = True

	if updated:
		ws.content = json.dumps(content)
		ws.module_onboarding = "Event Bookings Onboarding"

	# Always sync the charts child table to match all desired charts
	legacy_names = {"Monthly Events", "Event Revenue Trend"}
	ws.charts = [c for c in ws.charts if c.chart_name not in legacy_names]
	existing_chart_names = {c.chart_name for c in ws.charts}
	for chart_name, _ in desired_charts:
		if chart_name not in existing_chart_names:
			ws.append("charts", {"chart_name": chart_name, "label": chart_name})
			updated = True

	if updated:
		ws.save(ignore_permissions=True)
		frappe.db.commit()
		frappe.logger().info("event_bookings: workspace charts patched successfully")


def _fix_chart_filters_json():
	"""
	Normalise the date_field on the trend Dashboard Charts to 'booking_date'.
	Trends are measured by when a booking was made, not the (future) event
	date. Repairs legacy 'event_timing'/'event_date' values idempotently on
	every migrate. Also normalises dynamic_filters_json to static company.
	Replaces user-created from_date/to_date filters with fiscal_year so charts
	behave like ERPNext system charts and avoid filter hangs outside fiscal years.
	Run idempotently on every migrate.
	"""
	import json

	# Charts that aggregate by date and must use booking_date
	trend_charts = ["Event Booking Revenue Trends", "Event Booking Count Trends"]
	all_charts = trend_charts + ["Events By Event Type"]
	legacy_date_fields = {"event_timing", "event_date"}
	current_fy = get_fiscal_year_safe()

	for chart_name in all_charts:
		if not frappe.db.exists("Dashboard Chart", chart_name):
			continue

		raw = frappe.db.get_value("Dashboard Chart", chart_name, "filters_json") or "{}"
		try:
			stored = json.loads(raw)
		except (ValueError, TypeError):
			stored = {}

		changed = False

		# Fix date_field on trend charts
		if chart_name in trend_charts and stored.get("date_field") in legacy_date_fields:
			stored["date_field"] = "booking_date"
			changed = True

		# Remove any hardcoded company so the report uses the user's default
		# company instead of locking charts to a single company.
		if "company" in stored:
			stored.pop("company", None)
			changed = True

		# Remove user-defined from_date / to_date to prevent hangs when dates
		# fall outside any active Fiscal Year.
		for obsolete in ("from_date", "to_date"):
			if obsolete in stored:
				stored.pop(obsolete, None)
				changed = True

		# Add fiscal_year if missing and ERPNext provides one
		if "fiscal_year" not in stored and current_fy:
			stored["fiscal_year"] = current_fy
			changed = True

		if changed:
			frappe.db.set_value(
				"Dashboard Chart", chart_name, "filters_json",
				json.dumps(stored), update_modified=False,
			)

		# Strip dynamic JS expression from dynamic_filters_json
		raw_dyn = frappe.db.get_value("Dashboard Chart", chart_name, "dynamic_filters_json") or "{}"
		try:
			dyn = json.loads(raw_dyn)
		except (ValueError, TypeError):
			dyn = {}

		if dyn:
			frappe.db.set_value(
				"Dashboard Chart", chart_name, "dynamic_filters_json",
				"{}", update_modified=False,
			)

	frappe.db.commit()


def upgrade_designation_for_hrms():
	"""Upgrade Event Staff Requirement.designation from Data → Link(Designation) when
	HRMS is installed so users get full autocomplete from the HRMS Designation list.

	The DocType JSON ships the field as Data (Frappe-only baseline). This function
	promotes it to a proper Link at install/migrate time when HRMS is present.
	It is called on every after_migrate because bench migrate resets the field to
	the JSON baseline (Data) before this hook runs. Idempotent.
	"""
	if not is_hrms_installed():
		return
	if not frappe.db.exists("DocType", "Designation"):
		return

	current = frappe.db.get_value(
		"DocField",
		{"parent": "Event Staff Requirement", "fieldname": "designation"},
		"fieldtype",
	)
	if current == "Link":
		return  # already upgraded — nothing to do

	frappe.db.set_value(
		"DocField",
		{"parent": "Event Staff Requirement", "fieldname": "designation"},
		{"fieldtype": "Link", "options": "Designation"},
		update_modified=False,
	)
	frappe.db.commit()
	frappe.clear_cache(doctype="Event Staff Requirement")
	frappe.logger().info(
		"event_bookings: upgraded Event Staff Requirement.designation "
		"to Link(Designation) — HRMS is installed"
	)


def create_default_settings():
	"""Create one Event Booking Settings record per company (idempotent).
	Only called when ERPNext is installed — Company DocType must exist.
	"""
	for company in frappe.get_all("Company", pluck="name", limit_page_length=0):
		if not frappe.db.exists("Event Booking Settings", company):
			try:
				frappe.get_doc({
					"doctype": "Event Booking Settings",
					"company": company,
				}).insert(ignore_permissions=True)
			except (frappe.DuplicateEntryError, frappe.ValidationError):
				frappe.log_error(title=f"Failed to create Event Booking Settings for {company}")
	frappe.db.commit()


def create_custom_fields():
	"""
	Create Event Booking link fields on doctypes not covered by the
	Accounting Dimension auto-generation. Uses frappe.custom.doctype helpers
	so they are idempotent (safe to run multiple times).
	Skips any DocType that does not exist on this site.
	"""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_field

	fields = [
		# Doctype, fieldname, insert_after, extra kwargs
		("Quotation",           "event_booking", "title", {}),
		("Journal Entry",       "event_booking", "title", {}),
		("Material Request",    "event_booking", "title", {}),
		("Stock Reconciliation","event_booking", "title", {}),
	]

	for dt, fieldname, insert_after, extra in fields:
		if not frappe.db.exists("DocType", dt):
			continue

		df = {
			"fieldname": fieldname,
			"fieldtype": extra.get("fieldtype", "Link"),
			"label": extra.get("label", "Event Booking"),
			"options": "Event Booking" if extra.get("fieldtype", "Link") == "Link" else None,
			"insert_after": insert_after,
			"search_index": 1,
		}
		df.update({k: v for k, v in extra.items() if k not in ("fieldtype", "label")})

		try:
			create_custom_field(dt, df)
		except (frappe.DuplicateEntryError, frappe.ValidationError):
			frappe.log_error(title=f"Failed to create custom field {fieldname} on {dt}")


def create_accounting_dimension():
	"""Register Event Booking as an Accounting Dimension in ERPNext.
	Only called when ERPNext is installed — guarded by caller.
	"""
	try:
		if not frappe.db.exists("Accounting Dimension", "Event Booking"):
			doc = frappe.get_doc({
				"doctype": "Accounting Dimension",
				"document_type": "Event Booking",
				"label": "Event Booking",
				"disabled": 0,
			})
			doc.insert(ignore_permissions=True)
			frappe.db.commit()
	except (frappe.DuplicateEntryError, frappe.ValidationError):
		frappe.log_error(title="Failed to create Accounting Dimension for Event Booking")


def create_event_coa_accounts():
	"""
	Creates Event Revenue, Event COGS, and Event Damages Expense accounts
	under the company's existing Income and Expense root accounts.
	Does NOT assume hardcoded parent names — walks the COA tree dynamically.
	Only called when ERPNext is installed — guarded by caller.
	"""
	companies = frappe.get_all("Company", pluck="name", limit_page_length=0)
	for company in companies:
		income_root = _get_first_active_root("Income", company)

		expense_root = _get_first_active_root("Expense", company)
		if not income_root or not expense_root:
			frappe.log_error(f"Could not find Income/Expense roots for {company}", "Event Bookings Install")
			continue

		accounts = [
			{
				"account_name": "Event Revenue",
				"account_type": "Income Account",
				"root_type": "Income",
				"parent_account": income_root,
			},
			{
				"account_name": "Event COGS",
				"account_type": "Expense Account",
				"root_type": "Expense",
				"parent_account": expense_root,
			},
			{
				"account_name": "Event Damages Expenses",
				"account_type": "Expense Account",
				"root_type": "Expense",
				"parent_account": expense_root,
			},
		]

		for acc in accounts:
			account_name = f"{acc['account_name']} - {cstr(frappe.db.get_value('Company', company, 'abbr'))}"
			try:
				if not frappe.db.exists("Account", account_name):
					frappe.get_doc(
						{
							"doctype": "Account",
							"account_name": acc["account_name"],
							"company": company,
							"parent_account": acc["parent_account"],
							"root_type": acc["root_type"],
							"account_type": acc["account_type"],
							"is_group": 0,
						}
					).insert(ignore_permissions=True)
			except (frappe.DuplicateEntryError, frappe.ValidationError):
				frappe.log_error(title=f"Failed to create account {acc['account_name']} for {company}")

	frappe.db.commit()


def _get_first_active_root(root_type, company):
	"""Return the first group active account under the given root type."""
	return frappe.db.get_value(
		"Account",
		{"root_type": root_type, "company": company, "is_group": 1, "disabled": 0},
		"name",
		order_by="lft asc",
	)


def create_email_templates():
	"""Create default Email Templates for Event Bookings."""
	templates = [
		{
			"name": "Event Quotation",
			"subject": "Quotation for {{ doc.event_name or 'your event' }}",
			"response": """<p>Dear {{ doc.customer_name or 'Customer' }},</p>
<p>Please find attached our quotation for <strong>{{ doc.event_name or 'your event' }}</strong> scheduled for {{ doc.get_formatted('event_timing') or 'TBD' }}.</p>
<p>We look forward to your confirmation.</p>
<p>Best regards,<br>Events Team</p>""",
			"ref_doctype": "Quotation",
		},
		{
			"name": "Booking Confirmation",
			"subject": "Booking Confirmation - {{ doc.name }}",
			"response": """<p>Dear {{ doc.customer_name or 'Customer' }},</p>
<p>Your event booking <strong>{{ doc.name }}</strong> for <strong>{{ doc.event_name }}</strong> on {{ doc.get_formatted('event_timing') }} has been confirmed.</p>
<p>Location: {{ doc.event_location or 'TBD' }}</p>
<p>We look forward to making your event memorable!</p>
<p>Best regards,<br>Events Team</p>""",
			"ref_doctype": "Event Booking",
		},
	]

	for t in templates:
		if not frappe.db.exists("Email Template", t["name"]):
			try:
				frappe.get_doc(
					{
						"doctype": "Email Template",
						"name": t["name"],
						"subject": t["subject"],
						"response": t["response"],
						"ref_doctype": t["ref_doctype"],
						"owner": "Administrator",
					}
				).insert(ignore_permissions=True)
			except (frappe.DuplicateEntryError, frappe.ValidationError):
				frappe.log_error(title=f"Failed to create Email Template {t['name']}")

	frappe.db.commit()
