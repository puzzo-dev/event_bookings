app_name = "event_bookings"
app_title = "Event Bookings"
app_publisher = "I-Varse Technologies NG"
app_description = "Event Management"
app_email = "dev@itechnologies.ng"
app_license = "mit"

# Apps
# ------------------

# ERPNext and HRMS are optional — they unlock Quotation/SO/SI creation and
# Shift Assignment management respectively.  The app works on plain Frappe.
# required_apps = ["erpnext", "hrms"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "event_bookings",
# 		"logo": "/assets/event_bookings/logo.png",
# 		"title": "Event Bookings",
# 		"route": "/event_bookings",
# 		"has_permission": "event_bookings.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/event_bookings/css/event_bookings.css"
app_include_js = "/assets/event_bookings/js/workspace_conditional.js"

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
# doctype_js = {"doctype" : "public/js/doctype.js"}
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
# after_install = "event_bookings.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "event_bookings.uninstall.before_uninstall"
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

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
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
		"after_insert": "event_bookings.utils.google_calendar_sync.push_to_google_calendar",
		"on_update": "event_bookings.utils.google_calendar_sync.push_to_google_calendar",
		"on_trash": "event_bookings.utils.google_calendar_sync.delete_from_google_calendar",
	},
	"Quotation": {
		"on_submit": "event_bookings.utils.erpnext_hooks.on_quotation_submit",
		"on_update": "event_bookings.utils.erpnext_hooks.on_quotation_update",
		"on_cancel": "event_bookings.utils.erpnext_hooks.on_quotation_cancel",
	},
	"Sales Order": {
		"on_submit": "event_bookings.utils.erpnext_hooks.on_sales_order_submit",
		"on_update": "event_bookings.utils.erpnext_hooks.on_sales_order_update",
		"on_cancel": "event_bookings.utils.erpnext_hooks.on_sales_order_cancel",
	},
	"Sales Invoice": {
		"on_submit": "event_bookings.utils.erpnext_hooks.on_sales_invoice_submit",
		"on_update": "event_bookings.utils.erpnext_hooks.on_sales_invoice_update",
		"on_cancel": "event_bookings.utils.erpnext_hooks.on_sales_invoice_cancel",
	},
	"Stock Entry": {
		"on_submit": "event_bookings.utils.erpnext_hooks.on_stock_entry_submit",
		"on_cancel": "event_bookings.utils.erpnext_hooks.on_stock_entry_cancel",
	},
	"Shift Assignment": {
		"on_update": "event_bookings.utils.erpnext_hooks.on_shift_assignment_update",
	},
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"event_bookings.utils.scheduler.daily"
	],
	"hourly": [
		"event_bookings.utils.scheduler.hourly"
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

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

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

after_install = "event_bookings.install.after_install"

# Fixtures
# --------
fixtures = [
    {"dt": "Custom Field", "filters": [["dt", "in", [
        "Quotation", "Sales Order", "Sales Invoice",
        "Purchase Invoice", "Journal Entry",
        "Material Request", "Stock Entry", "Expense Claim",
        "Shift Assignment", "Cost Center"
    ]]]},
    {"dt": "Role", "filters": [["name", "in", ["Event Manager", "Event User"]]]},
    {"dt": "Workspace", "filters": [["name", "=", "Event Bookings"]]},
    {"dt": "Number Card", "filters": [["name", "in", [
        "Upcoming Events", "Events This Month", "Pending Invoices", "Total Revenue"
    ]]]},
    {"dt": "Dashboard Chart", "filters": [["name", "in", [
        "Monthly Events", "Event Revenue Trend",
        "Event Deals Completed", "Event Deals Lost",
        "Event Inquiry vs Conversion", "Event Lead Conversion Funnel",
    ]]]},
    {"dt": "Report", "filters": [["name", "in", ["Event Summary", "Event Revenue Trend"]]]},
]
