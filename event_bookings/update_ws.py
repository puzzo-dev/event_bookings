import frappe
import json

def update_workspace():
    ws_name = "Event Bookings"
    
    if frappe.db.exists("Workspace", ws_name):
        ws = frappe.get_doc("Workspace", ws_name)
    else:
        ws = frappe.new_doc("Workspace")
        ws.title = ws_name
        ws.name = ws_name
        ws.module = "Event Bookings"
        ws.is_standard = 1
        ws.public = 1

    ws.links = []
    
    # 1. Event Bookings Quick Links
    ws.append("links", {
        "type": "Link",
        "label": "Event Booking",
        "link_type": "DocType",
        "link_to": "Event Booking"
    })
    ws.append("links", {
        "type": "Link",
        "label": "Event Type",
        "link_type": "DocType",
        "link_to": "Event Type"
    })
    ws.append("links", {
        "type": "Link",
        "label": "Event Settings",
        "link_type": "DocType",
        "link_to": "Event Settings"
    })

    # 2. Sales Links
    ws.append("links", {
        "type": "Link",
        "label": "Sales Order",
        "link_type": "DocType",
        "link_to": "Sales Order"
    })
    ws.append("links", {
        "type": "Link",
        "label": "Sales Invoice",
        "link_type": "DocType",
        "link_to": "Sales Invoice"
    })
    ws.append("links", {
        "type": "Link",
        "label": "Quotation",
        "link_type": "DocType",
        "link_to": "Quotation"
    })
    
    # 3. Purchasing Links
    ws.append("links", {
        "type": "Link",
        "label": "Purchase Order",
        "link_type": "DocType",
        "link_to": "Purchase Order"
    })
    ws.append("links", {
        "type": "Link",
        "label": "Purchase Invoice",
        "link_type": "DocType",
        "link_to": "Purchase Invoice"
    })
    
    # Check if the report exists for the chart
    if frappe.db.exists("Report", "Event Booking Profitability"):
        # Create a Dashboard Chart if it doesn't exist
        chart_name = "Event Profitability Chart"
        if not frappe.db.exists("Dashboard Chart", chart_name):
            chart = frappe.get_doc({
                "doctype": "Dashboard Chart",
                "chart_name": chart_name,
                "chart_type": "Report",
                "report_name": "Event Booking Profitability",
                "type": "Bar",
                "timeseries": 0,
                "y_axis": [
                    {"y_field": "net_profit"}
                ],
                "use_report_chart": 1,
                "filters_json": "{}",
                "is_public": 1
            })
            chart.insert(ignore_permissions=True)
            
        # Dashboard Chart is created but not appended to ws.links (it will be embedded in content)
        pass

    # In v15, Workspaces are generated from links if no content is provided, 
    # but to be safe we can use standard Editor.js blocks
    content = [
        {
            "id": "head1",
            "type": "header",
            "data": {"text": "App Masters", "level": 4}
        },
        {
            "id": "card1",
            "type": "card",
            "data": {"card_name": "Event Bookings"}
        },
        {
            "id": "head2",
            "type": "header",
            "data": {"text": "Sales & Purchasing", "level": 4}
        },
        {
            "id": "card2",
            "type": "card",
            "data": {"card_name": "Sales & Purchasing"}
        }
    ]
    
    if frappe.db.exists("Report", "Event Booking Profitability"):
        content.append({
            "id": "chart1",
            "type": "chart",
            "data": {"chart_name": "Event Profitability Chart"}
        })

    ws.content = json.dumps(content)
    ws.save(ignore_permissions=True)
    frappe.db.commit()
    print("Workspace updated successfully!")

update_workspace()
