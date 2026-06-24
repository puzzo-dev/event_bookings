import frappe
from frappe.utils import cstr

from event_bookings.utils.seed import seed_event_types
from event_bookings.utils.helpers import erpnext_installed

# Private backup tables — plain MySQL, not Frappe DocTypes.
# Prefixed __eb_ so they are clearly internal and survive any app uninstall/reinstall.
_ERPNEXT_BACKUP_TABLE = "__eb_erpnext_link_backup"
_HRMS_BACKUP_TABLE = "__eb_hrms_link_backup"

# Site-config keys used to store the path of the Frappe partial backup file
# created before each uninstall.  Lets the user locate the file manually too.
_CONF_ERPNEXT_BACKUP = "event_bookings_erpnext_backup_path"
_CONF_HRMS_BACKUP = "event_bookings_hrms_backup_path"


# ---------------------------------------------------------------------------
# App lifecycle hooks
# ---------------------------------------------------------------------------

def after_install():
    """
    Hook executed after this app is freshly installed.
    Validates dependency coupling, seeds default data, and (if ERPNext is
    present) creates event-specific Chart of Accounts accounts.
    """
    _validate_dependency_coupling()
    seed_event_types()
    if erpnext_installed():
        create_event_coa_accounts()


def after_app_install(app):
    """
    Fires after *any* app is installed on this site.

    Handles two scenarios:
    1. Standalone → ERPNext+HRMS: both apps now present for the first time.
       Create CoA accounts for all existing companies.
    2. ERPNext+HRMS reinstall after a previous uninstall: backup tables may
       exist from before_app_uninstall.  Restore them now that the doctypes
       are live again.
    """
    if app not in ("erpnext", "hrms"):
        return

    installed = frappe.get_installed_apps()

    # Only act once both ERPNext and HRMS are present together.
    if "erpnext" not in installed or "hrms" not in installed:
        return

    # Restore any snapshots taken during a prior uninstall cycle.
    _restore_erpnext_links()
    _restore_hrms_links()

    # Ensure CoA accounts exist (idempotent — checks before creating).
    create_event_coa_accounts()


def before_app_uninstall(app):
    """
    Fires just before *any* app is uninstalled from this site.

    Does two things for each relevant app:
    1. Frappe partial backup — calls new_backup(include_doctypes=...) so a
       proper .sql.gz lands in the site's backups folder.  Stores the path
       in site config so the user can find it and, if needed, run
       frappe.installer.partial_restore(path) for a full table recovery.
    2. Raw SQL backup table — snapshots just the link column values into a
       private MySQL table (__eb_*).  This table survives the uninstall and
       is used by after_app_install for a surgical, row-by-row restore that
       does not overwrite any new bookings created in the interim.
    """
    if app == "erpnext":
        _frappe_partial_backup(
            doctypes="Event Booking,Event Assigned Staff",
            conf_key=_CONF_ERPNEXT_BACKUP,
        )
        _backup_erpnext_links()
        _null_erpnext_links()

    if app == "hrms":
        _frappe_partial_backup(
            doctypes="Event Assigned Staff",
            conf_key=_CONF_HRMS_BACKUP,
        )
        _backup_hrms_links()
        _null_hrms_links()


# ---------------------------------------------------------------------------
# Frappe-native partial backup (safety net / disaster recovery)
# ---------------------------------------------------------------------------

def _frappe_partial_backup(doctypes: str, conf_key: str):
    """
    Create a Frappe partial backup (.sql.gz) for the given doctypes and
    record the file path in site config.

    The file is a standard mysqldump that the user (or ops team) can inspect
    and restore manually with:
        bench --site <site> partial-restore <path>
    or programmatically with:
        frappe.installer.partial_restore(path)

    We do NOT use partial_restore in our own restore path because it replaces
    the entire table — any new Event Bookings created after the uninstall
    would be wiped.  Our __eb_* raw tables handle the selective column
    restore instead.
    """
    try:
        from frappe.utils.backups import new_backup

        odb = new_backup(
            include_doctypes=doctypes,
            ignore_files=True,
            force=True,
        )
        backup_path = odb.backup_path_db
        frappe.utils.update_site_config(conf_key, backup_path)
        frappe.logger().info(
            f"Event Bookings: Frappe partial backup written to {backup_path} "
            f"(key: {conf_key}).  Use frappe.installer.partial_restore(path) "
            f"for a full table recovery."
        )
    except Exception:
        frappe.log_error(title="Event Bookings: Frappe partial backup failed")


# ---------------------------------------------------------------------------
# ERPNext link backup / restore  (targeted column-level mechanism)
# ---------------------------------------------------------------------------

def _backup_erpnext_links():
    """
    Snapshot ERPNext-linked fields from tabEvent Booking into a private
    MySQL table before they are nulled.  A fresh DELETE clears any stale
    data from a previous uninstall cycle so repeated cycling works cleanly.
    """
    frappe.db.sql(f"""
        CREATE TABLE IF NOT EXISTS `{_ERPNEXT_BACKUP_TABLE}` (
            `eb_name`          VARCHAR(140) NOT NULL,
            `quotation`        VARCHAR(140),
            `sales_order`      VARCHAR(140),
            `sales_invoice`    VARCHAR(140),
            `material_request` VARCHAR(140),
            PRIMARY KEY (`eb_name`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    # Overwrite any data from a previous uninstall cycle.
    frappe.db.sql(f"DELETE FROM `{_ERPNEXT_BACKUP_TABLE}`")

    frappe.db.sql(f"""
        INSERT INTO `{_ERPNEXT_BACKUP_TABLE}`
            (eb_name, quotation, sales_order, sales_invoice, material_request)
        SELECT name, quotation, sales_order, sales_invoice, material_request
        FROM `tabEvent Booking`
        WHERE quotation        IS NOT NULL
           OR sales_order      IS NOT NULL
           OR sales_invoice    IS NOT NULL
           OR material_request IS NOT NULL
    """)

    count = frappe.db.sql(f"SELECT COUNT(*) FROM `{_ERPNEXT_BACKUP_TABLE}`")[0][0]
    frappe.logger().info(
        f"Event Bookings: backed up ERPNext links for {count} booking(s)."
    )


def _null_erpnext_links():
    """Null ERPNext-owned Link fields on Event Booking after backup."""
    for field in ("quotation", "sales_order", "sales_invoice", "material_request"):
        frappe.db.sql(
            f"UPDATE `tabEvent Booking` SET `{field}` = NULL WHERE `{field}` IS NOT NULL"
        )
    frappe.db.commit()
    frappe.logger().info("Event Bookings: nulled ERPNext link fields before ERPNext uninstall.")


def _restore_erpnext_links():
    """
    Restore ERPNext link values from the raw backup table after a reinstall.

    Only restores a value when the referenced document still exists in the
    newly reinstalled ERPNext — guards against dangling refs when the user
    started a fresh ERPNext install without restoring its data.

    Drops the backup table when done.  If the table does not exist (first
    install, or user already cleaned it up) the function is a no-op.
    """
    if not frappe.db.sql(f"SHOW TABLES LIKE '{_ERPNEXT_BACKUP_TABLE}'"):
        _log_frappe_backup_hint(_CONF_ERPNEXT_BACKUP)
        return

    rows = frappe.db.sql(
        f"SELECT eb_name, quotation, sales_order, sales_invoice, material_request "
        f"FROM `{_ERPNEXT_BACKUP_TABLE}`",
        as_dict=True,
    )
    if not rows:
        frappe.db.sql(f"DROP TABLE IF EXISTS `{_ERPNEXT_BACKUP_TABLE}`")
        return

    doctype_map = {
        "quotation":        "Quotation",
        "sales_order":      "Sales Order",
        "sales_invoice":    "Sales Invoice",
        "material_request": "Material Request",
    }

    restored = skipped = 0
    for row in rows:
        updates = {}
        for field, doctype in doctype_map.items():
            value = row.get(field)
            if value and frappe.db.exists(doctype, value):
                updates[field] = value

        if updates:
            set_clause = ", ".join(f"`{f}` = %s" for f in updates)
            frappe.db.sql(
                f"UPDATE `tabEvent Booking` SET {set_clause} WHERE name = %s",
                list(updates.values()) + [row.eb_name],
            )
            restored += 1
        else:
            skipped += 1

    frappe.db.sql(f"DROP TABLE IF EXISTS `{_ERPNEXT_BACKUP_TABLE}`")
    # Clear the conf key now that the backup table has been consumed.
    frappe.utils.update_site_config(_CONF_ERPNEXT_BACKUP, None)
    frappe.db.commit()

    frappe.logger().info(
        f"Event Bookings: restored ERPNext links for {restored} booking(s); "
        f"{skipped} skipped (referenced docs not found in reinstalled ERPNext — "
        f"use the Frappe partial backup for full recovery if needed)."
    )


# ---------------------------------------------------------------------------
# HRMS link backup / restore  (targeted column-level mechanism)
# ---------------------------------------------------------------------------

def _backup_hrms_links():
    """
    Snapshot HRMS staff data from tabEvent Assigned Staff into a private
    table before it is cleared.  Since employee/designation/shift_assignment
    are Data fields (plain strings), the values are always safe to restore
    without an existence check.
    """
    frappe.db.sql(f"""
        CREATE TABLE IF NOT EXISTS `{_HRMS_BACKUP_TABLE}` (
            `row_name`         VARCHAR(140) NOT NULL,
            `parent`           VARCHAR(140),
            `employee`         VARCHAR(140),
            `designation`      VARCHAR(140),
            `shift_assignment` VARCHAR(140),
            PRIMARY KEY (`row_name`)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """)

    frappe.db.sql(f"DELETE FROM `{_HRMS_BACKUP_TABLE}`")

    frappe.db.sql(f"""
        INSERT INTO `{_HRMS_BACKUP_TABLE}`
            (row_name, parent, employee, designation, shift_assignment)
        SELECT name, parent, employee, designation, shift_assignment
        FROM `tabEvent Assigned Staff`
        WHERE employee         IS NOT NULL
           OR shift_assignment IS NOT NULL
    """)

    count = frappe.db.sql(f"SELECT COUNT(*) FROM `{_HRMS_BACKUP_TABLE}`")[0][0]
    frappe.logger().info(
        f"Event Bookings: backed up HRMS staff data for {count} row(s)."
    )


def _null_hrms_links():
    """Clear HRMS staff data from Event Assigned Staff after backup."""
    frappe.db.sql(
        "UPDATE `tabEvent Assigned Staff` "
        "SET employee = NULL, designation = NULL, shift_assignment = NULL "
        "WHERE employee IS NOT NULL OR designation IS NOT NULL OR shift_assignment IS NOT NULL"
    )
    frappe.db.commit()
    frappe.logger().info("Event Bookings: cleared HRMS staff fields before HRMS uninstall.")


def _restore_hrms_links():
    """
    Restore HRMS staff strings from the backup table after a reinstall.
    No existence check needed — these are Data (string) fields, not Links.
    Drops the backup table when done.
    """
    if not frappe.db.sql(f"SHOW TABLES LIKE '{_HRMS_BACKUP_TABLE}'"):
        _log_frappe_backup_hint(_CONF_HRMS_BACKUP)
        return

    rows = frappe.db.sql(
        f"SELECT row_name, employee, designation, shift_assignment "
        f"FROM `{_HRMS_BACKUP_TABLE}`",
        as_dict=True,
    )
    if not rows:
        frappe.db.sql(f"DROP TABLE IF EXISTS `{_HRMS_BACKUP_TABLE}`")
        return

    for row in rows:
        frappe.db.sql(
            "UPDATE `tabEvent Assigned Staff` "
            "SET employee = %s, designation = %s, shift_assignment = %s "
            "WHERE name = %s",
            (row.employee, row.designation, row.shift_assignment, row.row_name),
        )

    frappe.db.sql(f"DROP TABLE IF EXISTS `{_HRMS_BACKUP_TABLE}`")
    frappe.utils.update_site_config(_CONF_HRMS_BACKUP, None)
    frappe.db.commit()
    frappe.logger().info(
        f"Event Bookings: restored HRMS staff data for {len(rows)} row(s)."
    )


def _log_frappe_backup_hint(conf_key: str):
    """
    If no raw backup table exists but a Frappe partial backup path was saved,
    log a hint so the operator knows a full-table recovery option is available.
    """
    path = frappe.conf.get(conf_key)
    if path:
        frappe.logger().info(
            f"Event Bookings: no raw backup table found for restore. "
            f"A Frappe partial backup exists at: {path}. "
            f"Run frappe.installer.partial_restore('{path}') for a full table recovery."
        )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# CoA account creation
# ---------------------------------------------------------------------------

def create_event_coa_accounts():
    """
    Creates Event Revenue, Event COGS, and Event Damages Expense accounts
    under the company's existing Income and Expense root accounts.
    Only runs when ERPNext is installed (Account doctype is ERPNext-owned).
    Idempotent — checks existence before inserting.
    """
    companies = frappe.get_all("Company", pluck="name")
    for company in companies:
        income_root = _get_first_active_root("Income", company)
        expense_root = _get_first_active_root("Expense", company)
        if not income_root or not expense_root:
            frappe.log_error(
                f"Could not find Income/Expense roots for {company}",
                "Event Bookings Install",
            )
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
            abbr = cstr(frappe.db.get_value("Company", company, "abbr"))
            account_name = f"{acc['account_name']} - {abbr}"
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
                frappe.log_error(
                    title=f"Failed to create account {acc['account_name']} for {company}"
                )

    frappe.db.commit()


def _get_first_active_root(root_type, company):
    return frappe.db.get_value(
        "Account",
        {"root_type": root_type, "company": company, "is_group": 1, "disabled": 0},
        "name",
        order_by="lft asc",
    )
