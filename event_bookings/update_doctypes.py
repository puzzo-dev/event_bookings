import frappe

def make_generic():
    # 1. Update Event Settings
    doc = frappe.get_doc("DocType", "Event Settings")
    
    # Remove cup-specific fields
    fields_to_remove = ["default_cup_item", "default_mixologist_item", "default_media_item", "default_cup_rate", "min_cup_order", "mixologist_fee"]
    doc.fields = [f for f in doc.fields if f.fieldname not in fields_to_remove]
    
    # Add generic fields if not exist
    if not any(f.fieldname == "default_rental_item" for f in doc.fields):
        doc.append("fields", {"fieldname": "default_rental_item", "label": "Default Rental Item", "fieldtype": "Link", "options": "Item", "insert_after": "enable_whatsapp"})
    if not any(f.fieldname == "default_service_item" for f in doc.fields):
        doc.append("fields", {"fieldname": "default_service_item", "label": "Default Service Item", "fieldtype": "Link", "options": "Item", "insert_after": "default_rental_item"})
    
    doc.save(ignore_permissions=True)
    
    # 2. Rename total_damages_cost to damages_cost if it exists on Event Booking
    doc_booking = frappe.get_doc("DocType", "Event Booking")
    for f in doc_booking.fields:
        if f.fieldname == "total_damages_cost":
            f.fieldname = "damages_cost"
            f.label = "Damages / Losses"

    doc_booking.save(ignore_permissions=True)

    # Add Custom Fields to Sales Order Item
    create_sales_order_item_fields()

def create_sales_order_item_fields():
    custom_fields = {
        "Sales Order Item": [
            {"fieldname": "qty_returned", "label": "Qty Returned", "fieldtype": "Float", "insert_after": "qty"},
            {"fieldname": "qty_damaged", "label": "Qty Damaged", "fieldtype": "Float", "insert_after": "qty_returned"},
            {"fieldname": "damage_fee", "label": "Damage Fee", "fieldtype": "Currency", "insert_after": "qty_damaged"}
        ]
    }
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields(custom_fields, ignore_validate=True)
    

    print('Updated successfully!')

make_generic()
