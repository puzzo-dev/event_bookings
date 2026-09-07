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


def get_permitted_companies(user=None):
    """Companies this user is confined to, or None when unrestricted.

    None mirrors get_event_booking_query's semantics: absent a Company User
    Permission there is nothing to restrict by, which is Frappe's own model.
    """
    if not user:
        user = frappe.session.user

    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return None

    companies = frappe.get_all(
        "User Permission",
        filters={"user": user, "allow": "Company"},
        pluck="for_value",
    )
    return companies or None


def validate_company_filter(filters):
    """Confine a Query Report's company filter to the user's User Permissions.

    Query Reports execute raw SQL, so neither permission_query_conditions nor
    User Permissions apply to them. Without this a user restricted to one
    company could name another in the filter and read its revenue — or leave
    the filter blank, which drops the company condition from the SQL entirely
    and returns every company at once.

    Mutates *filters* so a restricted user with a single permitted company gets
    it applied automatically rather than being asked for it.
    """
    allowed = get_permitted_companies()
    if allowed is None:
        return

    company = (filters or {}).get("company")

    if not company:
        if len(allowed) == 1:
            filters["company"] = allowed[0]
            return
        frappe.throw(
            frappe._("Select a Company to run this report."),
            frappe.PermissionError,
        )

    if company not in allowed:
        frappe.throw(
            frappe._("You do not have permission to report on {0}.").format(company),
            frappe.PermissionError,
        )


def has_event_booking_permission(doc, ptype="read", user=None, debug=False):
    """Apply the planner partition to *single-document* access.

    get_event_booking_query only constrains list and report queries. Frappe
    consults this hook for one document at a time, so implementing the query
    condition without a matching has_permission left every booking readable —
    and writable — by name: hidden from an Event Manager's list view, but
    served by /api/resource/Event Booking/<name>.

    Returns None for roles this partition does not govern, which frappe treats
    as "no opinion" and falls through to standard permissions. Company scoping
    is not repeated here: frappe applies Company User Permissions to single
    documents itself.
    """
    if not user:
        user = frappe.session.user

    roles = frappe.get_roles(user)
    if user == "Administrator" or "System Manager" in roles:
        return None

    # Only the planner roles are partitioned by Sales Partner. Sales/Accounts
    # users are governed by Company User Permissions alone.
    if not any(r in roles for r in ("Event Manager", "Event Assistant")):
        return None

    planner = getattr(doc, "event_planner", None)
    if not planner:
        return None  # unassigned bookings stay visible, as in the query condition

    return planner == _get_sales_partner_for_user(user)
