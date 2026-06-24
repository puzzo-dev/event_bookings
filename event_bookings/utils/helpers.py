import frappe


def erpnext_installed():
    """Return True if ERPNext is installed on this site."""
    return "erpnext" in frappe.get_installed_apps()


def hrms_installed():
    """Return True if HRMS is installed on this site."""
    return "hrms" in frappe.get_installed_apps()
