"""
Migrate data from the old `event_cost_center` column to the new `cost_center` column
on tabEvent Booking.

When the DocType JSON fieldname changed from `event_cost_center` to `cost_center`,
Frappe's schema sync adds the new column but leaves the old one in place.
This patch copies the data across so existing bookings retain their cost center.

Safe to run multiple times (idempotent WHERE clause).
"""

import frappe


def execute():
    # Only run if the old column still exists (i.e., this is an upgrade, not a clean install).
    columns = frappe.db.sql("SHOW COLUMNS FROM `tabEvent Booking` LIKE 'event_cost_center'")
    if not columns:
        return

    frappe.db.sql(
        """
        UPDATE `tabEvent Booking`
        SET `cost_center` = `event_cost_center`
        WHERE (`cost_center` IS NULL OR `cost_center` = '')
          AND `event_cost_center` IS NOT NULL
          AND `event_cost_center` != ''
        """
    )
    frappe.db.commit()
