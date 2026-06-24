import frappe
from frappe.utils import cstr

from event_bookings.utils.seed import seed_event_types


def after_install():
    """
    Hook executed after app is installed.
    Validates dependency coupling, seeds default data, and (if ERPNext is
    present) creates event-specific Chart of Accounts accounts.
    """
    _validate_dependency_coupling()
    seed_event_types()
    if _erpnext_installed():
        create_event_coa_accounts()


def after_app_install(app):
    """
    Hook called after *any* app is installed on this site.
    Used to react when ERPNext or HRMS is added to an existing standalone install.

    Scenario: site starts with Frappe + Event Bookings, then user later
    installs ERPNext+HRMS to unlock financial/staffing features.
    """
    if app not in ("erpnext", "hrms"):
        return

    installed = frappe.get_installed_apps()

    # Only act once both ERPNext and HRMS are present.
    if "erpnext" not in installed or "hrms" not in installed:
        return

    # Create CoA accounts for all existing companies now that ERPNext is live.
    create_event_coa_accounts()


def before_app_uninstall(app):
    """
    Hook called just before *any* app is uninstalled from this site.
    Used to protect Event Booking data when ERPNext or HRMS is removed.

    Scenario: user removes ERPNext/HRMS — the linked doctypes (Quotation,
    Sales Order, etc.) will be dropped.  Null out those references in Event
    Booking rows so existing records don't break on next open.
    """
    if app == "erpnext":
        _clear_erpnext_links()

    if app == "hrms":
        _clear_hrms_links()


def _clear_erpnext_links():
    """
    Null out ERPNext-owned Link field values stored on Event Booking rows.
    Called just before ERPNext is uninstalled so no dangling references remain.
    """
    erpnext_fields = [
        "quotation",
        "sales_order",
        "sales_invoice",
        "material_request",
    ]
    for field in erpnext_fields:
        frappe.db.sql(
            f"UPDATE `tabEvent Booking` SET `{field}` = NULL WHERE `{field}` IS NOT NULL"
        )

    frappe.db.commit()
    frappe.logger().info(
        "Event Bookings: cleared ERPNext link fields from Event Booking records "
        "before ERPNext uninstall."
    )


def _clear_hrms_links():
    """
    Null out HRMS-owned values stored in Event Assigned Staff child rows.
    Called just before HRMS is uninstalled.
    """
    frappe.db.sql(
        "UPDATE `tabEvent Assigned Staff` SET employee = NULL, designation = NULL, shift_assignment = NULL"
        " WHERE employee IS NOT NULL OR designation IS NOT NULL OR shift_assignment IS NOT NULL"
    )
    frappe.db.commit()
    frappe.logger().info(
        "Event Bookings: cleared HRMS link fields from Event Assigned Staff records "
        "before HRMS uninstall."
    )


def _validate_dependency_coupling():
    """
    ERPNext and HRMS must be installed together with this app.
    Installing ERPNext without HRMS leaves staff management non-functional.
    """
    installed = frappe.get_installed_apps()
    if "erpnext" in installed and "hrms" not in installed:
        frappe.throw(
            "HRMS is required when using Event Bookings with ERPNext. "
            "Please install HRMS alongside ERPNext before installing this app."
        )


def _erpnext_installed():
    return "erpnext" in frappe.get_installed_apps()


def create_event_coa_accounts():
    """
    Creates Event Revenue, Event COGS, and Event Damages Expense accounts
    under the company's existing Income and Expense root accounts.
    Only runs when ERPNext is installed (Account doctype is ERPNext-owned).
    """
    companies = frappe.get_all("Company", pluck="name")
    for company in companies:
        income_root = _get_first_active_root("Income", company)
        expense_root = _get_first_active_root("Expense", company)
        if not income_root or not expense_root:
            frappe.log_error(f"Could not find Income/Expense roots for {company}", "Event Bookings Install")
            continue

        accounts = [
            {
                "account_name": "Event Revenue",
                "account_type": "Income Account",
                "root_type": "Income",
                "parent_account": income_root,
            },
            {
                "account_name": "Event COGS",
                "account_type": "Expense Account",
                "root_type": "Expense",
                "parent_account": expense_root,
            },
            {
                "account_name": "Event Damages Expenses",
                "account_type": "Expense Account",
                "root_type": "Expense",
                "parent_account": expense_root,
            },
        ]

        for acc in accounts:
            account_name = f"{acc['account_name']} - {cstr(frappe.db.get_value('Company', company, 'abbr'))}"
            try:
                if not frappe.db.exists("Account", account_name):
                    frappe.get_doc(
                        {
                            "doctype": "Account",
                            "account_name": acc["account_name"],
                            "company": company,
                            "parent_account": acc["parent_account"],
                            "root_type": acc["root_type"],
                            "account_type": acc["account_type"],
                            "is_group": 0,
                        }
                    ).insert(ignore_permissions=True)
            except Exception:
                frappe.log_error(title=f"Failed to create account {acc['account_name']} for {company}")

    frappe.db.commit()


def _get_first_active_root(root_type, company):
    return frappe.db.get_value(
        "Account",
        {"root_type": root_type, "company": company, "is_group": 1, "disabled": 0},
        "name",
        order_by="lft asc",
    )
