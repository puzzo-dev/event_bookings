import frappe


def get_permission_query_conditions(user=None):
	"""Restrict Event Booking list to companies the user has access to.

	If the user has no Company User Permissions defined, no restriction is
	applied (they see all companies). System Managers are always unrestricted.
	"""
	if not user:
		user = frappe.session.user

	if "System Manager" in frappe.get_roles(user):
		return None

	user_companies = frappe.get_all(
		"User Permission",
		filters={"user": user, "allow": "Company"},
		pluck="for_value",
	)
	if not user_companies:
		return None

	escaped = ", ".join(frappe.db.escape(c) for c in user_companies)
	return f"`tabEvent Booking`.`company` in ({escaped})"
