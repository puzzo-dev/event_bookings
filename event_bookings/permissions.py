import frappe


def get_event_booking_query(user=None):
    """
    Row-level permission filter for Event Booking list and report views.

    Registered in hooks.py under `permission_query_conditions`.  Frappe appends
    the returned SQL fragment to every SELECT on tabEvent Booking for this user,
    so returning an empty string means "no additional restriction".

    Partitioning logic:
    - Administrator / System Manager: unrestricted.
    - All non-admin roles: company restriction applied when User Permissions exist.
    - Sales Manager / Sales User / Accounts User: company restriction only.
    - Event Manager / Event Assistant: company restriction AND planner restriction
      (own Sales Partner + unassigned bookings).
    """
    if not user:
        user = frappe.session.user

    roles = frappe.get_roles(user)

    if user == "Administrator" or "System Manager" in roles:
        return ""

    conditions = []

    # Company filter from User Permissions — applies to all non-admin roles.
    user_companies = frappe.get_all(
        "User Permission",
        filters={"user": user, "allow": "Company"},
        pluck="for_value",
    )
    if user_companies:
        escaped_companies = ", ".join(frappe.db.escape(c) for c in user_companies)
        conditions.append(f"`tabEvent Booking`.`company` IN ({escaped_companies})")

    if any(r in roles for r in ("Sales Manager", "Sales User", "Accounts User")):
        return " AND ".join(conditions)

    # Event Manager / Event Assistant: restrict to their own Sales Partner + unassigned.
    if any(r in roles for r in ("Event Manager", "Event Assistant")):
        partner = _get_sales_partner_for_user(user)
        if partner:
            escaped = frappe.db.escape(partner)
            # NOTE: the whole OR-group MUST stay parenthesised.  Frappe concatenates
            # this fragment into the WHERE clause with " and " WITHOUT adding parens
            # (see frappe/model/db_query.py), so an unwrapped `A OR B` would let the
            # OR escape any preceding AND conditions and leak rows across tenants.
            conditions.append(
                f"(`tabEvent Booking`.`event_planner` = {escaped}"
                f" OR `tabEvent Booking`.`event_planner` IS NULL"
                f" OR `tabEvent Booking`.`event_planner` = '')"
            )
        else:
            conditions.append(
                "(`tabEvent Booking`.`event_planner` IS NULL"
                " OR `tabEvent Booking`.`event_planner` = '')"
            )

    return " AND ".join(conditions)


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
