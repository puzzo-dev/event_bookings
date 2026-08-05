import json

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
	upgrade_designation_for_hrms()  # Link(Designation) when HRMS present, Data otherwise
	migrate_workspace_charts()     # ensure workspace references current charts


def after_migrate():
	"""
	Hook executed after every bench migrate.
	Cleans up any legacy is_standard charts that fixtures cannot delete,
	ensures the workspace content block always references the current charts,
	"""
	migrate_workspace_charts()
	cleanup_legacy_dashboard_name()
	from event_bookings.patches.drop_event_booking_settings import drop_orphan_onboarding_steps
	drop_orphan_onboarding_steps()
	patch_upcoming_events_number_card()
	repair_event_booking_dashboard_metadata()
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
	# App-created COA accounts.  These have no module link to Event Bookings,
	# so Frappe's module-based uninstall never removes them.
	_remove_event_coa_accounts()
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


def _remove_event_coa_accounts():
	"""Delete the Event Revenue, Event COGS, and Event Damages Expenses accounts
	created by ``create_event_coa_accounts``.  These are normal ledger accounts
	with no module link, so Frappe's module-based uninstall leaves them behind.
	"""
	if not frappe.db.exists("DocType", "Account"):
		return
	for account_name in ("Event Revenue", "Event COGS", "Event Damages Expenses"):
		for name in frappe.get_all("Account", filters={"account_name": account_name}, pluck="name"):
			_safe_delete("Account", name)


def _safe_delete(doctype, name):
	try:
		frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
	except Exception:
		frappe.log_error(title=f"event_bookings uninstall: failed to delete {doctype} {name}")


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

	# Workspace shows only the Event Booking Count Trends chart (full-width).
	# Remove any legacy or extra chart blocks from content.
	desired_chart = "Event Booking Count Trends"
	non_chart_blocks = [b for b in content if b.get("type") != "chart"]
	count_block = next(
		(b for b in content if b.get("type") == "chart" and b.get("data", {}).get("chart_name") == desired_chart),
		{"id": "cnt_chart01", "type": "chart", "data": {"chart_name": desired_chart, "col": 12}},
	)
	# Ensure the single chart block is full-width
	count_block.setdefault("data", {})["col"] = 12
	new_content = []
	for b in non_chart_blocks:
		new_content.append(b)
		# Insert chart block right after the onboarding block
		if b.get("type") == "onboarding" and not any(x.get("type") == "chart" for x in new_content):
			new_content.append(count_block)
	if not any(b.get("type") == "chart" for b in new_content):
		# No onboarding block present — prepend chart
		new_content.insert(1 if new_content else 0, count_block)

	if json.dumps(new_content) != json.dumps(content):
		content = new_content
		updated = True

	if updated:
		ws.content = json.dumps(content)
		ws.module_onboarding = "Event Bookings Onboarding"

	# Sync the charts child table — only the single count chart
	legacy_names = {"Monthly Events", "Event Revenue Trend", "Event Booking Revenue Trends", "Events By Event Type"}
	ws.charts = [c for c in ws.charts if c.chart_name not in legacy_names and c.chart_name == desired_chart]
	if not any(c.chart_name == desired_chart for c in ws.charts):
		ws.append("charts", {"chart_name": desired_chart, "label": desired_chart})
		updated = True

	# Sync the number cards.  These cannot be left to the code-backed workspace
	# JSON alone: frappe.model.sync imports that file through import_file_by_path,
	# which is hash-gated, so an unchanged file is skipped on every later migrate.
	# A site whose workspace was previously flattened (the old Workspace fixture
	# shipped number_cards: []) would therefore never get its cards back.
	if _sync_workspace_number_cards(ws, content):
		updated = True

	# Same story for shortcuts — the hash gate means a site can sit forever
	# without the Dashboard shortcut, and can keep rendering a block for a
	# shortcut that no longer exists.
	if _sync_workspace_shortcuts(ws, content):
		updated = True

	# v16 made `type` mandatory on Workspace (Workspace / Link / URL).  Sites whose
	# workspace row predates v16 carry NULL there, so the first ws.save() that ever
	# runs dies with MandatoryError — regardless of what changed.  Backfill it.
	if ws.meta.has_field("type") and not ws.get("type"):
		ws.type = "Workspace"
		updated = True

	if updated:
		ws.content = json.dumps(content)
		ws.save(ignore_permissions=True)
		frappe.db.commit()
		frappe.logger().info("event_bookings: workspace charts and number cards patched successfully")


DESIRED_NUMBER_CARDS = (
	"Upcoming Events",
	"Events This Month",
	"Pending Invoices",
	"Total Revenue",
)


def _sync_workspace_number_cards(ws, content):
	"""Ensure the four Key Metrics cards are on the workspace and in its content.

	Mutates *content* in place and returns True when anything changed.
	Cards whose Number Card record does not exist are skipped rather than
	appended, since a dangling reference renders as an empty widget.
	"""
	changed = False

	present = {c.number_card_name for c in ws.number_cards}
	for card in DESIRED_NUMBER_CARDS:
		if card in present or not frappe.db.exists("Number Card", card):
			continue
		ws.append("number_cards", {"number_card_name": card, "label": card})
		changed = True

	blocks = {
		b.get("data", {}).get("number_card_name")
		for b in content
		if b.get("type") == "number_card"
	}
	missing = [
		c for c in DESIRED_NUMBER_CARDS
		if c not in blocks and frappe.db.exists("Number Card", c)
	]
	if missing:
		# Place the cards after a "Key Metrics" header, mirroring the layout in
		# the code-backed workspace JSON.
		for i, b in enumerate(content):
			if b.get("type") == "header" and "Key Metrics" in str(b.get("data", {}).get("text", "")):
				insert_at = i + 1
				break
		else:
			# No header yet — add one directly after the chart block.
			chart_idx = next(
				(i for i, b in enumerate(content) if b.get("type") == "chart"), len(content) - 1
			)
			content.insert(chart_idx + 1, {
				"type": "header",
				"data": {"text": '<span class="h4"><b>Key Metrics</b></span>', "col": 12},
			})
			insert_at = chart_idx + 2

		for offset, card in enumerate(missing):
			content.insert(insert_at + offset, {
				"type": "number_card",
				"data": {"number_card_name": card, "col": 3},
			})
		changed = True

	return changed


# (label, type, link_to, doc_view, color) — the full desired shortcut set.
# Anything else on the workspace is legacy and gets removed.
DESIRED_SHORTCUTS = (
	("New Event Booking",        "DocType",   "Event Booking",  "New",  "blue"),
	("Event Bookings List",      "DocType",   "Event Booking",  "List", "green"),
	("Event Types",              "DocType",   "Event Type",     "List", "orange"),
	("Booking Review",           "DocType",   "Booking Review", "List", "pink"),
	("Event Bookings Dashboard", "Dashboard", "Event Bookings", "",     "blue"),
)


def _shortcut_target_exists(link_type, link_to):
	"""A shortcut pointing at a missing target renders as a dead tile."""
	if link_type == "DocType":
		return bool(frappe.db.exists("DocType", link_to))
	if link_type == "Dashboard":
		return bool(frappe.db.exists("Dashboard", link_to))
	return True


def _sync_workspace_shortcuts(ws, content):
	"""Ensure the workspace carries exactly the desired shortcuts, in order.

	Mutates *content* in place and returns True when anything changed.
	"""
	changed = False
	wanted = [s for s in DESIRED_SHORTCUTS if _shortcut_target_exists(s[1], s[2])]
	wanted_labels = [s[0] for s in wanted]

	# Drop legacy child rows (e.g. the removed Event Booking Settings shortcut).
	kept = [r for r in ws.shortcuts if r.label in wanted_labels]
	if len(kept) != len(ws.shortcuts):
		ws.shortcuts = kept
		changed = True

	present = {r.label for r in ws.shortcuts}
	for label, link_type, link_to, doc_view, color in wanted:
		if label in present:
			continue
		ws.append("shortcuts", {
			"label": label,
			"type": link_type,
			"link_to": link_to,
			"doc_view": doc_view,
			"color": color,
		})
		changed = True

	# Drop content blocks for shortcuts that no longer exist.
	stale = [
		b for b in content
		if b.get("type") == "shortcut"
		and b.get("data", {}).get("shortcut_name") not in wanted_labels
	]
	for b in stale:
		content.remove(b)
		changed = True

	blocks = {
		b.get("data", {}).get("shortcut_name")
		for b in content if b.get("type") == "shortcut"
	}
	missing = [l for l in wanted_labels if l not in blocks]
	if missing:
		# Append after the last existing shortcut block, else after the
		# "Shortcuts" header, else at the end.
		insert_at = len(content)
		for i, b in enumerate(content):
			if b.get("type") == "shortcut":
				insert_at = i + 1
			elif b.get("type") == "header" and "Shortcuts" in str(b.get("data", {}).get("text", "")):
				insert_at = max(insert_at, i + 1)
		for offset, label in enumerate(missing):
			content.insert(insert_at + offset, {
				"type": "shortcut",
				"data": {"shortcut_name": label, "col": 3},
			})
		changed = True

	return changed


def cleanup_legacy_dashboard_name():
	"""Remove duplicate dashboards, keeping the canonical 'Event Bookings' record.
	Fixtures create the dashboard as 'Event Bookings'; older records named
	'Event Booking' or 'Event Booking Dashboard' are deleted if present.
	"""
	canonical = "Event Bookings"
	duplicates = {"Event Booking", "Event Booking Dashboard"}

	if not frappe.db.exists("Dashboard", canonical):
		# Keep the existing record under a duplicate name until migrate creates the canonical one.
		return

	for name in duplicates:
		if frappe.db.exists("Dashboard", name):
			_safe_delete("Dashboard", name)
			frappe.logger().info(f"event_bookings: removed duplicate dashboard '{name}'")

	frappe.db.commit()


def patch_upcoming_events_number_card():
	"""Ensure the Upcoming Events number card counts future events that have
	advanced past negotiation (i.e. not Cancelled, New, Quoted or Negotiating).
	"""
	name = "Upcoming Events"
	if not frappe.db.exists("Number Card", name):
		return

	# Dynamic filter value is a JS expression eval'd client-side (see
	# frappe/public/js/frappe/utils/dashboard_utils.js get_all_filters).
	dynamic_filters = [["Event Booking", "event_date", ">=", "frappe.datetime.get_today()", False]]
	static_filters = [["Event Booking", "booking_status", "not in", "Cancelled,New,Quoted,Negotiating", False]]

	changed = False
	if frappe.db.get_value("Number Card", name, "filters_json") != json.dumps(static_filters):
		frappe.db.set_value("Number Card", name, "filters_json", json.dumps(static_filters))
		changed = True
	if frappe.db.get_value("Number Card", name, "dynamic_filters_json") != json.dumps(dynamic_filters):
		frappe.db.set_value("Number Card", name, "dynamic_filters_json", json.dumps(dynamic_filters))
		changed = True

	if changed:
		frappe.db.commit()
		frappe.logger().info("event_bookings: patched 'Upcoming Events' number card filters")


FALLBACK_DATE_FIELD = "event_date"


def repair_event_booking_dashboard_metadata():
	"""Repair Dashboard Charts / Number Cards that name a dead Event Booking field.

	``dashboard_chart.get`` builds its WHERE clause from ``Dashboard Chart.based_on``
	and from the fieldnames inside ``filters_json``.  If any of them no longer
	exists on the DocType, MariaDB raises "Unknown column" and the request 500s —
	which takes down the WHOLE dashboard, not just the offending widget.

	This supersedes the old per-card ``event_timing`` → ``event_date`` rewrite:
	it is driven by the DocType meta rather than a hardcoded field/name list, so
	it also covers any future rename.  Idempotent; safe to run on every migrate.
	"""
	if not frappe.db.exists("DocType", "Event Booking"):
		return

	# Real DB columns only.  get_valid_columns() = default_fields + data fields,
	# which is exactly the right test: both `based_on` and the filter fieldnames
	# end up as columns in the generated SQL.
	valid = set(frappe.get_meta("Event Booking").get_valid_columns())

	# ── Dashboard Chart.based_on ──────────────────────────────────────────
	for name, based_on in frappe.get_all(
		"Dashboard Chart",
		filters={"document_type": "Event Booking"},
		fields=["name", "based_on"],
		as_list=True,
	):
		if based_on and based_on not in valid:
			frappe.db.set_value(
				"Dashboard Chart", name, "based_on", FALLBACK_DATE_FIELD,
				update_modified=False,
			)
			frappe.logger().info(
				f"event_bookings: Dashboard Chart {name}: based_on "
				f"{based_on!r} -> {FALLBACK_DATE_FIELD!r}"
			)

	# ── list-shaped filters_json on both Charts and Cards ─────────────────
	for doctype in ("Dashboard Chart", "Number Card"):
		for name, raw in frappe.get_all(
			doctype,
			filters={"document_type": "Event Booking"},
			fields=["name", "filters_json"],
			as_list=True,
		):
			cleaned = _drop_unknown_filter_fields(raw, valid)
			if cleaned is not None:
				frappe.db.set_value(
					doctype, name, "filters_json", cleaned, update_modified=False,
				)
				frappe.logger().info(
					f"event_bookings: {doctype} {name}: dropped filters on removed fields"
				)

	# ── Number Card.aggregate_function_based_on ───────────────────────────
	for name, agg in frappe.get_all(
		"Number Card",
		filters={"document_type": "Event Booking"},
		fields=["name", "aggregate_function_based_on"],
		as_list=True,
	):
		if agg and agg not in valid:
			frappe.db.set_value(
				"Number Card", name, "aggregate_function_based_on", "name",
				update_modified=False,
			)
			frappe.logger().info(
				f"event_bookings: Number Card {name}: aggregate_function_based_on "
				f"{agg!r} -> 'name'"
			)

	frappe.db.commit()


def _drop_unknown_filter_fields(raw, valid):
	"""Return the cleaned ``filters_json`` string, or None when nothing changed.

	Only the list-of-lists schema (``[[doctype, fieldname, operator, value, ...]]``)
	used by Document Type charts and Number Cards is touched.  Report charts store
	a dict of report-filter names, which are not DocType fieldnames — those are
	handled separately by ``_fix_chart_filters_json``.
	"""
	try:
		stored = json.loads(raw or "[]")
	except (ValueError, TypeError):
		return None

	if not isinstance(stored, list):
		return None

	kept = [
		row for row in stored
		if not (isinstance(row, list) and len(row) >= 2 and row[1] not in valid)
	]
	return json.dumps(kept) if len(kept) != len(stored) else None


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

		# Defensive: legacy/corrupt filters_json can be a list; reset it so the
		# dict operations below don't raise AttributeError during migrate.
		if not isinstance(stored, dict):
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
