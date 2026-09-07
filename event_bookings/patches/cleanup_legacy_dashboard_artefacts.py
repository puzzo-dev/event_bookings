"""One-time cleanup of dashboard artefacts left behind by the fixture era.

Dashboard, Dashboard Chart, Dashboard Chart Source, Number Card, Notification
and Workspace records are now shipped from module folders and synced by
``frappe.model.sync`` / ``frappe.utils.dashboard.sync_dashboards``.  While they
were also shipped as fixtures, sites accumulated records that the new source of
truth no longer defines, plus a workspace that had been renamed in place.
Frappe's sync never deletes records it no longer ships, so sweep them once here
rather than re-patching on every migrate.
"""

import json

import frappe

# Superseded by native Frappe chart types / duplicate report charts.
OBSOLETE_CHART_SOURCES = [
	"Monthly Events",
	"Event Revenue Trend",
	"Event Deals Completed",
	"Event Deals Lost",
	# Converted to Report charts (module folders re-create them under the
	# same names); the Custom-source machinery is gone for good.
	"Event Inquiry vs Conversion",
	"Event Lead Conversion Funnel",
]

# Never fired: `event: "Custom"` with no caller.  The staffing shortfall digest
# is sent by event_bookings.utils.scheduler.send_unstaffed_alerts, which groups
# shortfalls across bookings — something a per-document Notification cannot do.
OBSOLETE_NOTIFICATIONS = ["Event Under-Staffed Alert"]

LEGACY_DASHBOARDS = ["Event Booking", "Event Booking Dashboard"]

# Charts the app no longer ships. "Event Revenue Trend" measured revenue by
# event_date ungrouped — the same measure as "Event Revenue Trend by Event Type"
# without the breakdown, and "Event Booking Revenue Trends" already covers the
# ungrouped view by booking_date.
OBSOLETE_CHARTS = ["Event Revenue Trend"]


def execute():
	_rename_legacy_workspace()
	_clear_stale_user_chart_config()
	_delete("Dashboard", LEGACY_DASHBOARDS)
	_delete("Notification", OBSOLETE_NOTIFICATIONS)
	# Charts must go before their sources — Dashboard Chart links to the source.
	_delete_charts_using_sources(OBSOLETE_CHART_SOURCES)
	_delete("Dashboard Chart", OBSOLETE_CHARTS)
	_delete("Dashboard Chart Source", OBSOLETE_CHART_SOURCES)


def _rename_legacy_workspace():
	"""The workspace shipped as "Event Bookings" before it became "Events Management"."""
	if not frappe.db.exists("Workspace", "Event Bookings"):
		return
	if frappe.db.exists("Workspace", "Events Management"):
		_delete("Workspace", ["Event Bookings"])
		return
	frappe.rename_doc("Workspace", "Event Bookings", "Events Management", force=True)
	frappe.db.set_value(
		"Workspace",
		"Events Management",
		{"label": "Events Management", "title": "Events Management"},
		update_modified=False,
	)


def _delete_charts_using_sources(sources):
	"""Drop Custom charts whose source is going away.

	``Monthly Events`` and ``Event Revenue Trend`` keep their names: they are
	re-created by the module folder as a native Count chart and a Report chart
	respectively, so only the stale Custom definition is removed here.
	"""
	names = frappe.get_all(
		"Dashboard Chart",
		filters={"chart_type": "Custom", "source": ("in", sources)},
		pluck="name",
	)
	_delete("Dashboard Chart", names)


def _delete(doctype, names):
	for name in names:
		if not frappe.db.exists(doctype, name):
			continue
		try:
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
		except Exception:
			frappe.log_error(title=f"event_bookings: failed to delete {doctype} {name}")


def _clear_stale_user_chart_config():
	"""Drop each user's saved filters for this module's charts.

	`Dashboard Settings.chart_config` caches per-user chart filters keyed by
	chart name.  Several charts changed `chart_type` (Custom -> Count / Report),
	and the saved filters kept the old shape: a JSON *object* where the new type
	expects a list.  `frappe.utils.parse_array` only checks `.length`, so an
	object passes straight through to
	`dashboard_chart.get`, where `filters.append(...)` resolves to None on a
	frappe._dict and raises "'NoneType' object is not callable" — a 500 on first
	render for every user who had ever set a filter.

	The saved values are stale by definition after a type change, so clear the
	entries for our charts and let each chart fall back to its own filters_json.
	"""
	chart_names = set(
		frappe.get_all("Dashboard Chart", filters={"module": "Event Bookings"}, pluck="name")
	)
	# Charts that existed under the old definitions but no longer do.
	chart_names.update(OBSOLETE_CHART_SOURCES)
	if not chart_names:
		return

	for name, raw in frappe.get_all(
		"Dashboard Settings", fields=["name", "chart_config"], as_list=True
	):
		if not raw:
			continue
		try:
			config = json.loads(raw)
		except (ValueError, TypeError):
			config = None
		if not isinstance(config, dict):
			# Unparseable or unexpected shape — reset rather than guess.
			frappe.db.set_value("Dashboard Settings", name, "chart_config", "{}", update_modified=False)
			continue

		cleaned = {k: v for k, v in config.items() if k not in chart_names}
		if len(cleaned) != len(config):
			frappe.db.set_value(
				"Dashboard Settings", name, "chart_config", json.dumps(cleaned), update_modified=False
			)
