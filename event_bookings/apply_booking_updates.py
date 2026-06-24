import frappe

def update_event_booking_doctype():
    frappe.init(site="erpnext-v15.local", sites_path="sites")
    frappe.connect()

    doc = frappe.get_doc("DocType", "Event Booking")
    
    # 1. Rename contact_person label to "Contact Person"
    for f in doc.fields:
        if f.fieldname == "contact_person":
            f.label = "Contact Person"
            break
            
    # 2. Add booking_date field
    # Check if it already exists
    if not any(f.fieldname == "booking_date" for f in doc.fields):
        insert_after = "event_name"
        doc.append("fields", {
            "fieldname": "booking_date",
            "label": "Booking Date",
            "fieldtype": "Date",
            "default": "Today",
            "insert_after": insert_after,
            "reqd": 1,
            "in_list_view": 1
        })
        
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    print("Event Booking doctype updated successfully.")

update_event_booking_doctype()
