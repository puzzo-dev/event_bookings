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

	# Authorisation check
	if not frappe.has_permission("Dashboard Chart", "write"):
		user_roles = set(frappe.get_roles())
		if not user_roles.intersection({"Event Manager", "System Manager"}):
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

	# Sanitise and persist
	allowed_keys = {"period", "based_on", "date_field", "from_date", "to_date", "company"}
	clean = {k: v for k, v in filters.items() if k in allowed_keys}

	frappe.db.set_value(
		"Dashboard Chart",
		chart_name,
		"filters_json",
		frappe.as_json(clean),
		update_modified=False,
	)

	return {"status": "ok", "filters": clean}
