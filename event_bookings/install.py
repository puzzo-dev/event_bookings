import frappe
from frappe.utils import cstr

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
	create_event_coa_accounts()
	create_email_templates()
	create_accounting_dimension()  # auto-creates system custom fields on SO, SI, SE, PI, EC
	create_custom_fields()         # creates remaining app custom fields
	migrate_workspace_charts()     # ensure workspace references current charts


def after_migrate():
	"""
	Hook executed after every bench migrate.
	Cleans up any legacy is_standard charts that fixtures cannot delete,
	and ensures the workspace content block always references the current charts.
	"""
	migrate_workspace_charts()


def migrate_workspace_charts():
	"""
	Idempotent: delete the old is_standard=1 charts (can't be removed by fixtures)
	and patch the workspace content to reference the new Report-based charts.
	"""
	import json

	# ── 1. Remove legacy charts ────────────────────────────────────────────
	legacy_charts = ["Event Revenue Trend", "Monthly Events"]
	for name in legacy_charts:
		if frappe.db.exists("Dashboard Chart", name):
			frappe.db.set_value("Dashboard Chart", name, "is_standard", 0)
			frappe.delete_doc("Dashboard Chart", name, force=True, ignore_missing=True)
			frappe.logger().info(f"event_bookings: deleted legacy chart '{name}'")

	# ── 2. Patch workspace content ─────────────────────────────────────────
	if not frappe.db.exists("Workspace", "Event Bookings"):
		return

	ws = frappe.get_doc("Workspace", "Event Bookings")

	# Parse existing content and replace any old chart references
	try:
		content = json.loads(ws.content or "[]")
	except (ValueError, TypeError):
		content = []

	chart_map = {
		"Event Revenue Trend":  "Event Booking Revenue Trends",
		"Monthly Events":       "Event Booking Count Trends",
	}

	updated = False
	for block in content:
		if block.get("type") == "chart":
			old_name = block.get("data", {}).get("chart_name")
			if old_name in chart_map:
				block["data"]["chart_name"] = chart_map[old_name]
				updated = True

	# Ensure the onboarding block is present at position 0
	has_onboarding = any(b.get("type") == "onboarding" for b in content)
	if not has_onboarding:
		content.insert(0, {
			"id": "onboard01",
			"type": "onboarding",
			"data": {"onboarding_name": "Event Bookings Onboarding", "col": 12},
		})
		updated = True

	if updated:
		ws.content = json.dumps(content)
		ws.module_onboarding = "Event Bookings Onboarding"
		# Sync the charts child table too
		ws.charts = [c for c in ws.charts if c.chart_name not in legacy_charts]
		existing_chart_names = {c.chart_name for c in ws.charts}
		for new_chart in ["Event Booking Revenue Trends", "Event Booking Count Trends"]:
			if new_chart not in existing_chart_names:
				ws.append("charts", {"chart_name": new_chart, "label": new_chart})
		ws.save(ignore_permissions=True)
		frappe.db.commit()
		frappe.logger().info("event_bookings: workspace charts patched successfully")


def create_custom_fields():
	"""
	Create Event Booking link fields on doctypes not covered by the
	Accounting Dimension auto-generation. Uses frappe.custom.doctype helpers
	so they are idempotent (safe to run multiple times).
	"""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_field

	fields = [
		# Doctype, fieldname, insert_after, extra kwargs
		("Quotation",           "event_booking", "title",              {}),
		("Journal Entry",       "event_booking", "title",              {}),
		("Material Request",    "event_booking", "title",              {}),
		("Stock Reconciliation","event_booking", "title",              {}),
		("Cost Center",         "is_event_cost_center", "disabled",   {"fieldtype": "Check", "label": "Is Event Cost Center"}),
	]

	for dt, fieldname, insert_after, extra in fields:
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
		except Exception:
			frappe.log_error(title=f"Failed to create custom field {fieldname} on {dt}")


def create_accounting_dimension():
	"""Register Event Booking as an Accounting Dimension in ERPNext."""
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
