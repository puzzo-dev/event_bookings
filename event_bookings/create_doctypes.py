import frappe

def create_doctypes():
    pass
    
    # 1. Event Settings (Single)
    if not frappe.db.exists("DocType", "Event Settings"):
        doc = frappe.get_doc({
            "doctype": "DocType",
            "name": "Event Settings",
            "module": "Event Bookings",
            "custom": 0,
            "issingle": 1,
            "fields": [
                {"fieldname": "default_rental_item", "label": "Default Rental Item", "fieldtype": "Link", "options": "Item"},
                {"fieldname": "default_service_item", "label": "Default Service Item", "fieldtype": "Link", "options": "Item"},
                {"fieldname": "cb_1", "fieldtype": "Column Break"},
                {"fieldname": "default_warehouse", "label": "Default Warehouse", "fieldtype": "Link", "options": "Warehouse"},
                {"fieldname": "sb_2", "fieldtype": "Section Break", "label": "Notifications"},
                {"fieldname": "default_shift_type", "label": "Default Shift Type", "fieldtype": "Link", "options": "Shift Type"},
                {"fieldname": "auto_create_project", "label": "Auto-Create Project", "fieldtype": "Check", "default": "0"},
                {"fieldname": "require_review", "label": "Require Post-Event Review", "fieldtype": "Check", "default": "0"},
                {"fieldname": "notification_email", "label": "Notification Email", "fieldtype": "Data"},
                {"fieldname": "enable_whatsapp", "label": "Enable WhatsApp", "fieldtype": "Check", "default": "0"}
            ]
        })
        doc.insert()
        print("Created Event Settings")

    # 2. Event Type
    if not frappe.db.exists("DocType", "Event Type"):
        doc = frappe.get_doc({
            "doctype": "DocType",
            "name": "Event Type",
            "module": "Event Bookings",
            "custom": 0,
            "naming_rule": "By fieldname",
            "autoname": "field:type_name",
            "fields": [
                {"fieldname": "type_name", "label": "Type Name", "fieldtype": "Data", "reqd": 1, "unique": 1},
                {"fieldname": "description", "label": "Description", "fieldtype": "Text"}
            ]
        })
        doc.insert()
        print("Created Event Type")

    # 4. Event Staff Requirement (Child Table)
    if not frappe.db.exists("DocType", "Event Staff Requirement"):
        doc = frappe.get_doc({
            "doctype": "DocType",
            "name": "Event Staff Requirement",
            "module": "Event Bookings",
            "custom": 0,
            "istable": 1,
            "fields": [
                {"fieldname": "designation", "label": "Designation", "fieldtype": "Link", "options": "Designation", "reqd": 1, "in_list_view": 1},
                {"fieldname": "qty_required", "label": "Qty Required", "fieldtype": "Int", "reqd": 1, "in_list_view": 1},
                {"fieldname": "qty_assigned", "label": "Qty Assigned", "fieldtype": "Int", "read_only": 1, "in_list_view": 1},
                {"fieldname": "notes", "label": "Notes", "fieldtype": "Text"}
            ]
        })
        doc.insert()
        print("Created Event Staff Requirement")

    # 5. Event Assigned Staff (Child Table)
    if not frappe.db.exists("DocType", "Event Assigned Staff"):
        doc = frappe.get_doc({
            "doctype": "DocType",
            "name": "Event Assigned Staff",
            "module": "Event Bookings",
            "custom": 0,
            "istable": 1,
            "fields": [
                {"fieldname": "employee", "label": "Employee", "fieldtype": "Link", "options": "Employee", "in_list_view": 1, "read_only": 1},
                {"fieldname": "employee_name", "label": "Employee Name", "fieldtype": "Data", "fetch_from": "employee.employee_name", "read_only": 1},
                {"fieldname": "designation", "label": "Designation", "fieldtype": "Link", "options": "Designation", "in_list_view": 1, "read_only": 1},
                {"fieldname": "shift_date", "label": "Shift Date", "fieldtype": "Date", "read_only": 1},
                {"fieldname": "shift_assignment", "label": "Shift Assignment", "fieldtype": "Link", "options": "Shift Assignment", "read_only": 1, "in_list_view": 1}
            ]
        })
        doc.insert()
        print("Created Event Assigned Staff")

    # 6. Event Booking (Standard)
    if not frappe.db.exists("DocType", "Event Booking"):
        doc = frappe.get_doc({
            "doctype": "DocType",
            "name": "Event Booking",
            "module": "Event Bookings",
            "custom": 0,
            "is_submittable": 0,
            "track_changes": 1,
            "track_views": 1,
            "autoname": "format:EVT-.YYYY.-.####",
            "naming_rule": "Expression",
            "fields": [
                {"fieldname": "sec_core", "label": "Client & Event Core", "fieldtype": "Section Break"},
                {"fieldname": "event_name", "label": "Event Name", "fieldtype": "Data", "reqd": 1, "in_list_view": 1},
                {"fieldname": "booking_status", "label": "Booking Status", "fieldtype": "Select", "options": "New\nQuoted\nNegotiating\nConfirmed\nIn Preparation\nExecuted\nInvoiced\nPaid\nCancelled", "reqd": 1, "default": "New", "in_list_view": 1},
                {"fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer", "reqd": 1},
                {"fieldname": "contact_person", "label": "Contact", "fieldtype": "Link", "options": "Contact"},
                {"fieldname": "col_type", "fieldtype": "Column Break"},
                {"fieldname": "event_type", "label": "Event Type", "fieldtype": "Link", "options": "Event Type", "reqd": 1},
                {"fieldname": "event_planner", "label": "Event Planner", "fieldtype": "Link", "options": "Sales Partner"},
                {"fieldname": "event_cost_center", "label": "Cost Center", "fieldtype": "Link", "options": "Cost Center"},
                {"fieldname": "project", "label": "Project", "fieldtype": "Link", "options": "Project"},
                
                {"fieldname": "sec_logistics", "label": "Logistics & Schedule", "fieldtype": "Section Break"},
                {"fieldname": "event_date", "label": "Event Date", "fieldtype": "Date", "reqd": 1, "in_list_view": 1},
                {"fieldname": "event_time", "label": "Event Time", "fieldtype": "Time", "reqd": 1},
                {"fieldname": "event_end_time", "label": "Event End Time", "fieldtype": "Time"},
                {"fieldname": "guest_count", "label": "Guest Count", "fieldtype": "Int"},
                {"fieldname": "col_loc", "fieldtype": "Column Break"},
                {"fieldname": "event_location", "label": "Event Location", "fieldtype": "Small Text", "reqd": 1},
                {"fieldname": "special_requirements", "label": "Special Requirements", "fieldtype": "Text"},
                
                {"fieldname": "sec_services", "label": "Services & Financials", "fieldtype": "Section Break"},
                {"fieldname": "total_estimated", "label": "Total Estimated", "fieldtype": "Currency", "read_only": 1},
                {"fieldname": "total_actual", "label": "Total Actual", "fieldtype": "Currency", "read_only": 1},
                {"fieldname": "col_fin", "fieldtype": "Column Break"},
                {"fieldname": "quotation", "label": "Quotation", "fieldtype": "Link", "options": "Quotation", "read_only": 1},
                {"fieldname": "sales_order", "label": "Sales Order", "fieldtype": "Link", "options": "Sales Order", "read_only": 1},
                {"fieldname": "sales_invoice", "label": "Sales Invoice", "fieldtype": "Link", "options": "Sales Invoice", "read_only": 1},
                {"fieldname": "material_request", "label": "Material Request", "fieldtype": "Link", "options": "Material Request", "read_only": 1},
                
                {"fieldname": "sec_staffing", "label": "Staffing", "fieldtype": "Section Break"},
                {"fieldname": "staff_requirements", "label": "Staff Requirements", "fieldtype": "Table", "options": "Event Staff Requirement"},
                {"fieldname": "assigned_staff", "label": "Assigned Staff", "fieldtype": "Table", "options": "Event Assigned Staff"},
                
                {"fieldname": "sb_post_event", "fieldtype": "Section Break", "label": "Post-Event"},
                {"fieldname": "total_damage_assessment", "label": "Total Damage Assessment", "fieldtype": "Currency", "read_only": 1},
                {"fieldname": "cb_post", "fieldtype": "Column Break"},
                {"fieldname": "client_feedback", "label": "Client Feedback", "fieldtype": "Text"},
                {"fieldname": "review_requested", "label": "Review Requested", "fieldtype": "Check"},
                {"fieldname": "review_received", "label": "Review Received", "fieldtype": "Check"}
            ]
        })
        doc.insert()
        print("Created Event Booking")
    frappe.db.commit()
    print("Done!")
