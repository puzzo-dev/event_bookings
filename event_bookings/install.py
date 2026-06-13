import frappe
from frappe.utils import cstr


def after_install():
	"""
	Hook executed after app is installed.
	- Seeds default Event Types
	- Creates event-specific Chart of Accounts accounts
	"""
	seed_event_types()
	create_event_coa_accounts()


def seed_event_types():
	"""Create default Event Type records if none exist."""
	default_types = ["Wedding", "Corporate", "Birthday", "Conference", "Private Party"]
	for t in default_types:
		if not frappe.db.exists("Event Type", t):
			frappe.get_doc({"doctype": "Event Type", "type_name": t}).insert(ignore_permissions=True)
	frappe.db.commit()


def create_event_coa_accounts():
	"""
	Creates Event Revenue, Event COGS, and Event Breakage Expense accounts
	under the company's existing Income and Expense root accounts.
	Does NOT assume hardcoded parent names — walks the COA tree dynamically.
	"""
	companies = frappe.get_all("Company", pluck="name")
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
				"account_name": "Event Damage Expenses",
				"account_type": "Expense Account",
				"root_type": "Expense",
				"parent_account": expense_root,
			},
		]

		for acc in accounts:
			account_name = f"{acc['account_name']} - {cstr(frappe.db.get_value('Company', company, 'abbr'))}"
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

	frappe.db.commit()


def _get_first_active_root(root_type, company):
	"""Return the first group active account under the given root type."""
	return frappe.db.get_value(
		"Account",
		{"root_type": root_type, "company": company, "is_group": 1, "disabled": 0},
		"name",
		order_by="lft asc",
	)
