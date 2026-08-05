# Event Bookings

A standalone Frappe app for managing event lifecycles, integrated with **ERPNext** and **HRMS**.

## Overview

Event Bookings manages the full event lifecycle from enquiry to post-event follow-up, while leveraging ERPNext for financials/stock and HRMS for staff management.

## Dependencies

- Frappe Framework v15+
- ERPNext
- HRMS

## Installation

```bash
bench get-app https://github.com/your-org/event_bookings.git
bench --site your-site.local install-app event_bookings
```

## Features

### DocTypes
- **Event Booking** — Central operational document for every event
- **Event Type** — Dynamic classification (Wedding, Corporate, etc.)
- **Event Service Item** — Child table for line items
- **Event Staff Requirement** — Roles needed vs assigned
- **Event Assigned Staff** — Read-only view of assigned employees

### Workflow
9-state workflow: New → Quoted → Negotiating → Confirmed → In Preparation → Executed → Invoiced → Paid → Cancelled

### Integration
- **ERPNext**: Quotations, Sales Orders, Sales Invoices, Material Requests, Stock Entries
- **HRMS**: Shift Assignments for staff scheduling
- **Accounting**: Dynamic COA account creation (Event Revenue, COGS, Breakage Expenses)

### Dashboard
- Custom workspace with KPIs, charts, and shortcuts
- Query report: Event Booking Profitability

## Configuration

The app ships with no settings DocType — there is nothing to configure after
install. Notifications are configured per-doctype from the Desk:

1. **Email** — Settings > Notification (e.g. *Days Before* on `event_date`)
2. **WhatsApp** — WhatsApp Notification (frappe_whatsapp), same per-doctype model
3. Seeded **Event Types** can be edited under the Event Bookings workspace

## License

MIT
