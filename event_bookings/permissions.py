import frappe


def get_event_booking_query(user=None):
    """
    Row-level permission filter for Event Booking list and report views.

    Registered in hooks.py under `permission_query_conditions`.  Frappe appends
    the returned SQL fragment to every SELECT on tabEvent Booking for this user,
    so returning an empty string means "no additional restriction".

    Partitioning logic:
    - Administrator / System Manager: unrestricted.
    - Sales Manager / Sales User / Accounts User: unrestricted (cross-planner visibility).
    - Event Manager: sees all bookings where event_planner matches their linked
      Sales Partner, PLUS bookings with no planner assigned.  This keeps the
      role meaningful on multi-planner sites while still allowing managers to
      see unassigned work.
    - Event User (read-only role): same filter as Event Manager so they cannot
      accidentally browse other planners' data.
    """
    if not user:
        user = frappe.session.user

    roles = frappe.get_roles(user)

    # Unrestricted roles.
    if user == "Administrator" or "System Manager" in roles:
        return ""
    if any(r in roles for r in ("Sales Manager", "Sales User", "Accounts User")):
        return ""

    # Event Manager / Event User: restrict to their own Sales Partner + unassigned.
    if any(r in roles for r in ("Event Manager", "Event User")):
        partner = _get_sales_partner_for_user(user)
        if partner:
            escaped = frappe.db.escape(partner)
            return (
                f"(`tabEvent Booking`.`event_planner` = {escaped}"
                f" OR `tabEvent Booking`.`event_planner` IS NULL"
                f" OR `tabEvent Booking`.`event_planner` = '')"
            )
        # No linked Sales Partner — show only unassigned bookings.
        return (
            "`tabEvent Booking`.`event_planner` IS NULL"
            " OR `tabEvent Booking`.`event_planner` = ''"
        )

    # Fallback: no additional restriction for any other role.
    return ""


def _get_sales_partner_for_user(user):
    """
    Return the Sales Partner name linked to this user, or None.

    Sales Partners store a `user` Link field that maps a portal/desk user to
    a partner record.  If the site does not use Sales Partners for planners
    this function returns None and the caller falls back gracefully.
    """
    try:
        return frappe.db.get_value("Sales Partner", {"user": user}, "name")
    except Exception:
        return None
