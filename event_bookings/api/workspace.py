import frappe
from frappe import _


@frappe.whitelist()
def update_chart_filters(chart_name, filters):
	"""
	Update the filters_json of a Dashboard Chart.

	Only users with write permission on 'Dashboard Chart' DocType
	or members of 'Event Manager' / 'System Manager' roles may update.
	"""
	if isinstance(filters, str):
		import json
		filters = json.loads(filters)

	# A list-shaped payload (the legacy filters_json schema, or any hand-rolled
	# caller) would reach .items() below and raise
	# "AttributeError: 'list' object has no attribute 'items'" as a raw 500.
	if not isinstance(filters, dict):
		frappe.throw(_("Chart filters must be a JSON object of fieldname/value pairs."))

	# Authorisation check — require write permission on Dashboard Chart or
	# an elevated role. Role membership is checked only to avoid forcing
	# a full "write" permission grant on a core doctype just for filter edits.
	has_doc_write = frappe.has_permission("Dashboard Chart", "write")
	has_role = bool(set(frappe.get_roles()).intersection({"Event Manager", "System Manager"}))
	if not has_doc_write and not has_role:
		frappe.throw(
			_("You do not have permission to edit chart filters."),
			frappe.PermissionError,
		)

	# Validate the chart exists and belongs to our module
	chart = frappe.db.get_value(
		"Dashboard Chart",
		chart_name,
		["name", "module"],
		as_dict=True,
	)
	if not chart:
		frappe.throw(_("Dashboard Chart '{0}' not found.").format(chart_name))

	if chart.module != "Event Bookings":
		frappe.throw(_("Only Event Bookings charts can be edited here."))

	# Sanitise and persist — only known safe filter keys are accepted
	allowed_keys = {"period", "based_on", "date_field", "fiscal_year", "company"}
	clean = {k: v for k, v in filters.items() if k in allowed_keys}

	frappe.db.set_value(
		"Dashboard Chart",
		chart_name,
		"filters_json",
		frappe.as_json(clean),
		update_modified=False,
	)

	return {"status": "ok", "filters": clean}
