import frappe


def has_app_permission():
	"""Return True if the current user can see the Event Bookings app in the app switcher."""
	return bool(
		set(frappe.get_roles()).intersection(
			{"System Manager", "Event Manager", "Event Assistant"}
		)
	)
