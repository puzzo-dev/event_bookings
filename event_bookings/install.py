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
	"""
	seed_event_types()
	create_event_coa_accounts()
	create_email_templates()
	create_accounting_dimension()


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
