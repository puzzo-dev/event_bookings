app_name = "event_bookings"
app_title = "Events Management"
app_publisher = "I-Varse Technologies NG"
app_description = "Event Management"
app_email = "dev@itechnologies.ng"
app_license = "mit"
app_icon = "/assets/event_bookings/images/logo.svg"
app_logo_url = "/assets/event_bookings/images/logo.svg"
favicon = "/assets/event_bookings/images/logo.png"

# Apps
# ------------------

# ERPNext and HRMS are optional — they unlock Quotation/SO/SI creation and
# Shift Assignment management respectively.  The app works on plain Frappe.
# required_apps = ["erpnext", "hrms"]

def _desk_route() -> str:
	"""Where the Desk lives on this version of Frappe.

	v16 moved it from /app to /desk. A stale "/app" still arrives, through the
	website_redirects rule v16 ships, but it costs a redirect and it fails
	frappe.apps.is_desk_apps(), which matches routes against ^/desk. That check
	feeds get_default_path(), so a single non-/desk route makes the whole site's
	post-login landing page fall through to "/apps" — itself only a redirect to
	/desk on v16. ERPNext changed its own hook to "/desk" for the same reason.

	Resolved here rather than forked per branch so the v15 and v16 lines stay
	one codebase. Falls back to the v15 route: it works on both, and a version
	string that cannot be parsed is no reason to fail loading hooks.
	"""
	try:
		import frappe

		return "/desk" if int(frappe.__version__.split(".", 1)[0]) >= 16 else "/app"
	except Exception:
		return "/app"


# Each item in the list will be shown as an app in the apps page.
#
# On v16 this no longer renders anywhere: frappe/www/apps.* was deleted, /apps
# redirects to /desk, and nothing in the Desk iterates boot.apps_data.apps —
# the only two readers are hardcoded lookups for "crm" and "helpdesk" that draw
# promotional banners. The hook still feeds boot and the login landing page, so
# it is kept and kept correct; on v16 the app is reached through its Events
# Management workspace instead of an app tile.
add_to_apps_screen = [
	{
		"name": "event_bookings",
		"logo": "/assets/event_bookings/images/logo.svg",
		"title": "Events Management",
		"route": _desk_route(),
		"has_permission": "event_bookings.api.permission.has_app_permission"
	}
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/event_bookings/css/event_bookings.css"
# app_include_js = "/assets/event_bookings/js/event_bookings.js"

# include js, css files in header of web template
# web_include_css = "/assets/event_bookings/css/event_bookings.css"
# web_include_js = "/assets/event_bookings/js/event_bookings.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "event_bookings/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# Quotation-first flow: adds Create → Event Booking to the Quotation form.
doctype_js = {
    "Quotation": "public/js/quotation.js",
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "event_bookings/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "event_bookings.utils.jinja_methods",
# 	"filters": "event_bookings.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "event_bookings.install.before_install"
after_install = "event_bookings.install.after_install"
after_migrate = "event_bookings.install.after_migrate"

# Uninstallation
# ------------

before_uninstall = "event_bookings.install.before_uninstall"
# after_uninstall = "event_bookings.uninstall.after_uninstall"

# Integration Setup — react when sibling apps are installed or removed
# ------------------
after_app_install = "event_bookings.install.after_app_install"
before_app_uninstall = "event_bookings.install.before_app_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "event_bookings.utils.before_app_install"
# after_app_install = "event_bookings.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "event_bookings.utils.before_app_uninstall"
# after_app_uninstall = "event_bookings.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "event_bookings.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

permission_query_conditions = {
	"Event Booking": "event_bookings.permissions.get_event_booking_query",
}

# permission_query_conditions governs list/report queries only. Without the
# matching has_permission hook the planner partition was list-only, and any
# booking could still be fetched by name over /api/resource.
has_permission = {
	"Event Booking": "event_bookings.permissions.has_event_booking_permission",
}

# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

doc_events = {
	"Event Booking": {
		"on_update": "event_bookings.utils.google_calendar_sync.push_to_google_calendar",
		# Frappe runs on_update_after_submit — NOT on_update — once a document is
		# submitted (frappe/model/document.py: run_post_save_methods). status
		# is the only meaningfully editable field after submit and it appears in the
		# calendar event body, so without this the Google Calendar entry froze at the
		# status the booking had when it was submitted, cancellations included.
		"on_update_after_submit": "event_bookings.utils.google_calendar_sync.push_to_google_calendar",
		# on_cancel fires on docstatus 1→2. Frappe does NOT run on_update or
		# on_update_after_submit on cancel, so without this the Google Calendar
		# event remained active indefinitely after a booking was cancelled.
		"on_cancel": "event_bookings.utils.google_calendar_sync.push_to_google_calendar",
		"on_trash": "event_bookings.utils.google_calendar_sync.delete_from_google_calendar",
	},
	"Quotation": {
		"validate": "event_bookings.utils.erpnext_hooks.validate_event_booking_link",
		"on_submit": "event_bookings.utils.erpnext_hooks.on_quotation_submit",
		"on_update": "event_bookings.utils.erpnext_hooks.on_quotation_update",
		"on_cancel": "event_bookings.utils.erpnext_hooks.on_quotation_cancel",
	},
	"Sales Order": {
		"validate": "event_bookings.utils.erpnext_hooks.validate_event_booking_link",
		"before_save": "event_bookings.utils.erpnext_hooks.on_sales_order_before_save",
		"on_submit": "event_bookings.utils.erpnext_hooks.on_sales_order_submit",
		"on_update": "event_bookings.utils.erpnext_hooks.on_sales_order_update",
		"on_cancel": "event_bookings.utils.erpnext_hooks.on_sales_order_cancel",
	},
	"Sales Invoice": {
		"validate": "event_bookings.utils.erpnext_hooks.validate_event_booking_link",
		"before_save": "event_bookings.utils.erpnext_hooks.on_sales_invoice_before_save",
		"on_submit": "event_bookings.utils.erpnext_hooks.on_sales_invoice_submit",
		"on_update": "event_bookings.utils.erpnext_hooks.on_sales_invoice_update",
		"on_cancel": "event_bookings.utils.erpnext_hooks.on_sales_invoice_cancel",
	},
	# Stock Entry is the document that actually moves goods for an event, so the
	# booking's Service Items table is rebuilt from it rather than typed. Tagging
	# Event Booking on the entry is the whole interface — it does not matter
	# whether the entry came from the booking's own button or was raised by hand
	# in the warehouse.
	"Stock Entry": {
		"on_submit": "event_bookings.utils.erpnext_hooks.on_stock_entry_change",
		"on_cancel": "event_bookings.utils.erpnext_hooks.on_stock_entry_change",
		"on_trash": "event_bookings.utils.erpnext_hooks.on_stock_entry_change",
		"on_update_after_submit": "event_bookings.utils.erpnext_hooks.on_stock_entry_change",
	},
	"Shift Assignment": {
		"on_update": "event_bookings.utils.erpnext_hooks.on_shift_assignment_update",
		# qty_assigned is a full recount of *submitted* Shift Assignments, so it
		# has to run whenever one leaves that set. Frappe dispatches on_cancel —
		# not on_update — for docstatus 1->2 (run_post_save_methods), so without
		# this a cancelled assignment left the booking reading as fully staffed.
		"on_cancel": "event_bookings.utils.erpnext_hooks.on_shift_assignment_update",
		# on_trash is belt-and-braces: Frappe refuses to delete a submitted
		# record, so the row is already cancelled (and already excluded) by the
		# time this runs. Kept so the recount stays correct if the docstatus
		# filter above is ever widened.
		"on_trash": "event_bookings.utils.erpnext_hooks.on_shift_assignment_update",
	},
	"Payment Entry": {
		"validate": "event_bookings.utils.erpnext_hooks.validate_event_booking_link",
		"on_submit": "event_bookings.utils.erpnext_hooks.on_payment_entry_submit",
		# There was no cancel counterpart: a payment could take a booking to
		# Paid and then be cancelled, leaving the booking Paid against an
		# invoice that was outstanding again.
		"on_cancel": "event_bookings.utils.erpnext_hooks.on_payment_entry_cancel",
	},
	# Journal Entries settle invoices without creating a Payment Entry, so the
	# Payment Entry hook alone leaves those bookings stuck at Invoiced.
	"Journal Entry": {
		"on_submit": "event_bookings.utils.erpnext_hooks.on_journal_entry_submit",
	},
	"Accounting Dimension": {
		"on_update": "event_bookings.utils.erpnext_hooks.on_accounting_dimension_update",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"event_bookings.utils.scheduler.auto_execute_passed_events",
		"event_bookings.utils.scheduler.send_unstaffed_alerts",
	],
}

# Testing
# -------

# before_tests = "event_bookings.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "event_bookings.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "event_bookings.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["event_bookings.utils.before_request"]
# after_request = ["event_bookings.utils.after_request"]

# Job Events
# ----------
# before_job = ["event_bookings.utils.before_job"]
# after_job = ["event_bookings.utils.after_job"]

# User Data Protection
# --------------------

user_data_fields = [
	{
		"doctype": "Event Booking",
		"filter_by": "customer",
		"redact_fields": ["customer", "special_requirements"],
		"partial": 1,
	},
]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"event_bookings.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

# Fixtures
# --------
fixtures = [
    # Only records Frappe cannot sync from module folders belong here.
    #
    # Workspace, Dashboard Chart Source, Notification, Report, Print Format,
    # Onboarding Step and Module Onboarding are synced from
    # event_bookings/event_bookings/<doctype>/ by frappe.model.sync
    # (IMPORTABLE_DOCTYPES); Dashboard, Dashboard Chart and Number Card are
    # synced from event_bookings/event_bookings/{dashboard_chart,number_card,
    # event_bookings_dashboard}/ by frappe.utils.dashboard.sync_dashboards.
    # Shipping any of them as fixtures too gives two sources of truth that
    # silently overwrite each other on every migrate.
    {"dt": "Custom Field", "filters": [["dt", "in", [
        "Quotation", "Sales Order", "Sales Invoice",
        "Material Request", "Stock Entry",
        "Shift Assignment", "Cost Center"
    ]]]},
    {"dt": "Role", "filters": [["name", "in", ["Event Manager", "Event Assistant"]]]},
]
