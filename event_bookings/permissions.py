import frappe


def get_event_booking_query(user=None):
    """
    Row-level permission filter for Event Booking list and report views.

    Registered in hooks.py under `permission_query_conditions`.  Frappe appends
    the returned SQL fragment to every SELECT on tabEvent Booking for this user,
    so returning an empty string means "no additional restriction".

    Current behaviour: no additional restriction for any role.  System Managers
    and Administrators always see all records.

    Extension point for multi-company or planner-based partitioning:
    replace the empty returns below with a SQL WHERE fragment, e.g.

        return f"`tabEvent Booking`.`event_planner` = {frappe.db.escape(partner)}"

    once the exact partitioning requirements are confirmed.
    """
    if not user:
        user = frappe.session.user

    # System Manager and Administrator: unrestricted access.
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return ""

    # All other roles: no additional row filter for now.
    # TODO: add company/planner-based partitioning here when requirements are defined.
    return ""
