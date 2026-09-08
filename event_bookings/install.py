import frappe
from frappe.utils import cstr

from event_bookings.utils.erpnext_bridge import is_erpnext_installed, is_hrms_installed
from event_bookings.utils.seed import seed_event_types


def after_install():
	"""
	Hook executed after app is installed.
	- Seeds default Event Types
	- Creates event-specific Chart of Accounts accounts
	- Creates default Email Templates
	- Repairs the standard Notification module files
	- Registers Event Booking as an Accounting Dimension
	- Creates custom fields on native doctypes
	"""
	seed_event_types()
	create_email_templates()
	# Same check migrate makes. A fresh install gets its notification files from
	# the checkout, but a partial or packaged install may not, and a standard
	# Notification with no module file fails the save that triggers it.
	_repair_standard_notifications()
	if is_erpnext_installed():
		create_event_coa_accounts()    # requires Account + Company DocTypes
		create_accounting_dimension()  # auto-creates system custom fields on SO, SI, SE, PI, EC
		create_custom_fields()         # creates remaining app custom fields
		create_default_settings()      # one Event Booking Settings record per company
	upgrade_designation_for_hrms()  # Link(Designation) when HRMS present, Data otherwise


def after_migrate():
	"""
	Hook executed after every bench migrate.

	Dashboards, Dashboard Charts, Number Cards, Chart Sources, Notifications and
	the Workspace are deliberately NOT touched here: Frappe syncs them from the
	module folders (frappe.model.sync.IMPORTABLE_DOCTYPES and
	frappe.utils.dashboard.sync_dashboards), which are the single source of
	truth.  One-off repairs for legacy sites belong in event_bookings/patches/,
	not in a hook that re-runs on every migrate.

	What remains: Event Booking Settings for companies added after install, and
	the HRMS Designation field upgrade (bench migrate resets it to the JSON
	baseline before this hook runs).
	"""
	# Standard Notifications: Frappe imports a module file for each one before
	# sending, and a missing file does not skip the alert — it raises inside the
	# save that triggered it. The two reminders here are scheduled, so a missing
	# file would break the scheduler rather than a form, which is quieter and
	# worse. Written back if absent.
	_repair_standard_notifications()

	if is_erpnext_installed():
		create_default_settings()
	upgrade_designation_for_hrms()  # re-apply on every migrate — JSON resets it to Data


# ---------------------------------------------------------------------------
# Sibling-app integration hooks (wired in hooks.py) — fire when ANY app on the
# site is installed/uninstalled.  They MUST exist: frappe.get_attr resolves the
# dotted path for every app install/uninstall, so a missing function raises
# AttributeError and aborts the operation site-wide.
# ---------------------------------------------------------------------------

def after_app_install(app_name):
	"""Set up ERPNext/HRMS integration when those apps arrive AFTER event_bookings."""
	if app_name == "erpnext" and is_erpnext_installed():
		create_event_coa_accounts()
		create_accounting_dimension()
		create_custom_fields()
		create_default_settings()
	elif app_name == "hrms" and is_hrms_installed():
		create_custom_fields()          # (re)create Shift Assignment.event_booking
		upgrade_designation_for_hrms()


def before_app_uninstall(app_name):
	"""Tear down our ERPNext/HRMS integration objects before a sibling app is removed,
	so nothing we added dangles once that app's doctypes disappear."""
	if app_name == "erpnext":
		_remove_accounting_dimension()
		_remove_event_booking_custom_fields()
	elif app_name == "hrms":
		_remove_custom_field("Shift Assignment", "event_booking")


def before_uninstall():
	"""event_bookings' own uninstall cleanup.

	Frappe deletes this app's modules and DocTypes automatically, but it does NOT
	remove the artefacts we added to CORE / ERPNext doctypes.  Left behind, the
	``event_booking`` Link custom fields and the Accounting Dimension keep pointing
	at the now-deleted ``Event Booking`` DocType and raise
	"DocType Event Booking not found" on every affected form.  Remove them here.
	"""
	# Accounting Dimension first: ERPNext's on_trash removes the event_booking
	# custom fields it generated on Sales Order / Sales Invoice / Stock Entry / etc.
	_remove_accounting_dimension()
	# Sweep any remaining Event Booking link fields and the legacy cost-center marker.
	_remove_event_booking_custom_fields()
	_remove_custom_field_by_fieldname("is_event_cost_center")
	# App-created Email Templates.
	for template_name in ("Event Quotation", "Booking Confirmation"):
		if frappe.db.exists("Email Template", template_name):
			_safe_delete("Email Template", template_name)
	# App-owned roles.  Roles have no `module` link, so Frappe's module-based
	# uninstall never removes them — they must be swept explicitly.  force=True
	# also clears the associated Has Role assignments.
	for role in ("Event Manager", "Event Assistant"):
		if frappe.db.exists("Role", role):
			_safe_delete("Role", role)
	frappe.db.commit()


def _remove_accounting_dimension():
	if not frappe.db.exists("DocType", "Accounting Dimension"):
		return
	if frappe.db.exists("Accounting Dimension", "Event Booking"):
		_safe_delete("Accounting Dimension", "Event Booking")


def _remove_event_booking_custom_fields():
	"""Delete every Custom Field whose fieldname is ``event_booking`` (our marker),
	regardless of which doctype it was attached to."""
	_remove_custom_field_by_fieldname("event_booking")


def _remove_custom_field_by_fieldname(fieldname):
	for name in frappe.get_all("Custom Field", filters={"fieldname": fieldname}, pluck="name"):
		_safe_delete("Custom Field", name)


def _remove_custom_field(doctype, fieldname):
	name = f"{doctype}-{fieldname}"
	if frappe.db.exists("Custom Field", name):
		_safe_delete("Custom Field", name)


def _safe_delete(doctype, name):
	try:
		frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
	except Exception:
		frappe.log_error(title=f"event_bookings uninstall: failed to delete {doctype} {name}")


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
	"""Ensure the Event Booking Settings Single doctype exists with defaults.
	The Single record is auto-created by Frappe on first save — this just
	seeds sensible defaults if the record doesn't exist yet.
	"""
	if not frappe.db.exists("Event Booking Settings", "Event Booking Settings"):
		frappe.get_doc({"doctype": "Event Booking Settings"}).insert(ignore_permissions=True)
		frappe.db.commit()


def create_custom_fields():
	"""
	Create Event Booking link fields on doctypes not covered by the
	Accounting Dimension auto-generation. Uses frappe.custom.doctype helpers
	so they are idempotent (safe to run multiple times).
	Skips any DocType that does not exist on this site.

	Also hides the event_booking field on child tables (auto-created by the
	Accounting Dimension) — the link belongs on the parent document, not on
	individual line items.
	"""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_field

	fields = [
		# Doctype, fieldname, insert_after, extra kwargs
		# Quotation: the event_booking link is the reverse-link write-back target
		# (set server-side by make_event_booking after_insert). It is hidden and
		# read-only — the quotation-first flow means users create the booking FROM
		# the quotation, never the other way around.
		("Quotation",           "event_booking", "title", {"hidden": 1, "read_only": 1}),
		("Journal Entry",       "event_booking", "company", {}),
		("Stock Reconciliation","event_booking", "cost_center", {}),
		# HRMS Shift Assignment is not an accounting doc, so it is not covered by
		# the Accounting Dimension auto-field. Needed for staff-count sync and
		# cancellation cascade. Skipped automatically when HRMS is not installed.
		("Shift Assignment",    "event_booking", "shift_type", {}),
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

	# Clean up event_booking fields: delete from irrelevant doctypes,
	# hide on child tables, reposition visible ones after 'project'.
	_cleanup_event_booking_fields()


def _cleanup_event_booking_fields():
	"""Fix the placement and existence of event_booking custom fields.

	The Accounting Dimension auto-creates event_booking on ~50 doctypes
	(parents + child tables + tools). Most are irrelevant to the event
	workflow. This function:

	1. DELETES event_booking from doctypes that have no business linking
	   to an Event Booking (Material Request, Asset, POS, Subcontracting,
	   etc.). Gone completely — not hidden.
	2. Hides event_booking on child tables (line items) — the link
	   belongs on the parent document, not individual rows. These are kept
	   (hidden) because the Accounting Dimension needs them for line-item
	   dimension tracking.
	3. Repositions the visible parent fields to sit after 'project'
	   (or 'cost_center' where project doesn't exist), following the
	   same layout pattern ERPNext uses for dimension fields.
	"""

	# --- DELETE completely: no business reason to link to Event Booking ---
	delete_dts = [
		"Material Request",
		"Material Request Item",
		"Advance Taxes and Charges",
		"Asset",
		"Asset Capitalization",
		"Asset Depreciation Schedule",
		"Asset Movement Item",
		"Asset Repair",
		"Asset Value Adjustment",
		"Budget",
		"Leave Encashment",
		"Loyalty Program",
		"Opening Invoice Creation Tool",
		"Opening Invoice Creation Tool Item",
		"Payment Request",
		"Payroll Entry",
		"POS Invoice",
		"POS Invoice Item",
		"POS Profile",
		"Shipping Rule",
		"Subscription",
		"Subscription Plan",
		"Supplier Quotation",
		"Supplier Quotation Item",
		"Account Closing Balance",
		"Subcontracting Order",
		"Subcontracting Order Item",
		"Subcontracting Receipt",
		"Subcontracting Receipt Item",
	]

	# --- HIDE (keep for accounting, not visible on form) ---
	hide_dts = [
		"Stock Entry Detail",
		"Sales Order Item",
		"Sales Invoice Item",
		"Purchase Order Item",
		"Purchase Invoice Item",
		"Delivery Note Item",
		"Purchase Receipt Item",
		"Journal Entry Account",
		"Expense Claim Detail",
		"Sales Taxes and Charges",
		"Purchase Taxes and Charges",
		"Expense Taxes and Charges",
		"Landed Cost Item",
		"Payment Entry Deduction",
		"Payment Reconciliation Allocation",
		"GL Entry",
		"Payment Ledger Entry",
		"Payment Reconciliation",
	]

	# --- VISIBLE: reposition after project (ERPNext dimension pattern) ---
	reposition = {
		"Stock Entry": "project",
		"Sales Order": "project",
		"Sales Invoice": "project",
		"Payment Entry": "project",
		"Delivery Note": "project",
		"Purchase Order": "project",
		"Purchase Invoice": "project",
		"Purchase Receipt": "project",
		"Expense Claim": "project",
		"Journal Entry": "cost_center",
		"Stock Reconciliation": "cost_center",
		"Shift Assignment": "shift_type",
	}

	# Delete irrelevant
	for dt in delete_dts:
		if not frappe.db.exists("DocType", dt):
			continue
		cf_name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": "event_booking"})
		if not cf_name:
			continue
		try:
			frappe.delete_doc("Custom Field", cf_name)
		except Exception:
			frappe.log_error(title=f"Failed to delete event_booking on {dt}")

	# Hide child tables and system tables
	for dt in hide_dts:
		if not frappe.db.exists("DocType", dt):
			continue
		cf_name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": "event_booking"})
		if not cf_name:
			continue
		try:
			cf = frappe.get_doc("Custom Field", cf_name)
			if not cf.hidden:
				cf.hidden = 1
				cf.save(ignore_permissions=True)
		except (frappe.DuplicateEntryError, frappe.ValidationError):
			frappe.log_error(title=f"Failed to hide event_booking on {dt}")

	# Reposition visible
	for dt, insert_after in reposition.items():
		if not frappe.db.exists("DocType", dt):
			continue
		cf_name = frappe.db.get_value("Custom Field", {"dt": dt, "fieldname": "event_booking"})
		if not cf_name:
			continue
		try:
			cf = frappe.get_doc("Custom Field", cf_name)
			cf.insert_after = insert_after
			cf.hidden = 0
			cf.read_only = 0
			cf.save(ignore_permissions=True)
		except (frappe.DuplicateEntryError, frappe.ValidationError):
			frappe.log_error(title=f"Failed to reposition event_booking on {dt}")


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
<p>Please find attached our quotation for <strong>{{ doc.event_name or 'your event' }}</strong>.</p>
<p>We look forward to your confirmation.</p>
<p>Best regards,<br>Events Team</p>""",
			"ref_doctype": "Quotation",
		},
		{
			"name": "Booking Confirmation",
			"subject": "Booking Confirmation - {{ doc.name }}",
			"response": """<p>Dear {{ doc.customer_name or 'Customer' }},</p>
<p>Your event booking <strong>{{ doc.name }}</strong> for <strong>{{ doc.event_name }}</strong> on {{ doc.get_formatted('event_date') }} has been confirmed.</p>
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



def _repair_standard_notifications():
	"""Repair the notification packages this app ships, and demote orphans.

	The app is the source of truth for its standard Notifications: whatever is
	in ``event_bookings/notification/`` is the complete set. The repair runs in
	that direction only — over the folders on disk, writing back the package
	files a partial checkout or a restored backup might be missing.

	It used to run the other way as well, writing a folder for any database
	record marked standard and exporting the record into it. That resurrects
	what a release removed: ``frappe.model.sync`` walks the module folder and
	imports every JSON it finds, so an exported orphan is re-created on the next
	migrate, and the app now carries a file for a notification it does not ship.

	A standard record with no shipped definition is demoted to non-standard
	instead. That stops the failing import immediately — the import only happens
	for standard records — leaves the alert working, and deletes nothing.
	"""
	import importlib
	import os

	for module in ("Event Bookings",):
		try:
			base = os.path.join(frappe.get_module_path(module), "notification")
		except Exception:
			continue

		shipped = _shipped_notification_slugs(base)
		repaired = []

		if shipped:
			_ensure_package(base)

		for slug in shipped:
			folder = os.path.join(base, slug)
			_ensure_package(folder)
			leaf = os.path.join(folder, f"{slug}.py")
			if not os.path.exists(leaf):
				with open(leaf, "w"):
					pass
				repaired.append(slug)

		demoted = []
		for name in frappe.get_all(
			"Notification", filters={"module": module, "is_standard": 1}, pluck="name"
		):
			if frappe.scrub(name) in shipped:
				continue
			frappe.db.set_value("Notification", name, "is_standard", 0, update_modified=False)
			demoted.append(name)

		if repaired:
			importlib.invalidate_caches()

		if demoted:
			frappe.log_error(
				title="Event Bookings: demoted orphaned standard notifications",
				message=(
					"These Notifications were marked standard but this release does not "
					"ship a definition for them: "
					+ ", ".join(demoted)
					+ ". They are now ordinary Notifications — they still run, and they "
					"no longer fail the saves they are attached to. Delete them if they "
					"are left over from an older release."
				),
			)


def _shipped_notification_slugs(base: str) -> set:
	"""Notification folders the app actually ships — those carrying a definition.

	A folder holding only package files defines nothing; it is residue from the
	export this function used to perform, so it does not count as shipped.
	"""
	import os

	if not os.path.isdir(base):
		return set()
	return {
		entry
		for entry in os.listdir(base)
		if os.path.isfile(os.path.join(base, entry, f"{entry}.json"))
	}


def _ensure_package(path: str):
	import os

	os.makedirs(path, exist_ok=True)
	init = os.path.join(path, "__init__.py")
	if not os.path.exists(init):
		with open(init, "w"):
			pass
