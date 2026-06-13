"""
Utility: verify_cost_center
Run via: bench --site <site> execute event_bookings.utils.verify_cost_center.run
"""
import frappe


def run():
    """End-to-end verification of per-event cost center feature."""
    results = {}

    # 1. Check field exists in meta (works for Single DocTypes)
    meta = frappe.get_meta("Event Settings")
    results["event_settings_field_exists"] = bool(
        meta.get_field("auto_create_cost_center_per_event")
    )

    # 2. Check custom field on Cost Center
    results["cost_center_custom_field"] = bool(
        frappe.db.exists("Custom Field", "Cost Center-is_event_cost_center")
    )

    # 3. Check Event Settings values (uses tabSingles)
    results["auto_create_enabled"] = bool(
        frappe.db.get_single_value("Event Settings", "auto_create_cost_center_per_event")
    )
    results["default_cost_center"] = frappe.db.get_single_value(
        "Event Settings", "default_cost_center"
    )

    # 4. Count event-specific cost centers
    results["event_cost_centers_in_db"] = frappe.db.count(
        "Cost Center", {"is_event_cost_center": 1}
    )

    # 5. Recent event bookings
    results["recent_bookings"] = frappe.db.get_all(
        "Event Booking",
        fields=["name", "event_name", "booking_status", "event_cost_center"],
        limit=5,
        order_by="creation desc",
    )

    for k, v in results.items():
        print(f"  {k}: {v}")

    return results


def test_create_event():
    """Create a test event booking and confirm it to verify per-event cost center creation."""
    cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
    customer = "_Test CC Verify Customer"
    if not frappe.db.exists("Customer", customer):
        frappe.get_doc({
            "doctype": "Customer",
            "customer_name": customer,
            "customer_type": "Individual",
            "customer_group": cg,
        }).insert(ignore_permissions=True)

    event_type = "_Test Verify"
    if not frappe.db.exists("Event Type", event_type):
        frappe.get_doc({"doctype": "Event Type", "type_name": event_type}).insert(
            ignore_permissions=True
        )

    eb = frappe.get_doc({
        "doctype": "Event Booking",
        "event_name": "Per-Event CC Verification",
        "customer": customer,
        "event_type": event_type,
        "event_date": frappe.utils.add_days(frappe.utils.today(), 21),
        "event_time": "18:00:00",
        "event_location": "Test Venue",
        "booking_status": "New",
    })
    eb.insert(ignore_permissions=True)
    print(f"Created: {eb.name}")
    print(f"Cost center after insert: {eb.event_cost_center!r}")

    eb.booking_status = "Confirmed"
    eb.save(ignore_permissions=True)
    print(f"Cost center after Confirmed: {eb.event_cost_center}")

    if eb.event_cost_center:
        cc = frappe.get_doc("Cost Center", eb.event_cost_center)
        print(f"  is_event_cost_center: {cc.is_event_cost_center}")
        print(f"  parent_cost_center: {cc.parent_cost_center}")
        print(f"  company: {cc.company}")

    frappe.db.commit()
    return eb.name
