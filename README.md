# Event Bookings

A Frappe custom app for managing event lifecycles, integrated with **ERPNext** (Selling, Stock, Accounts) and **HRMS** (Staff Scheduling).

## Overview

Event Bookings manages the full event lifecycle — from customer inquiry through quoting, confirmation, staffing, execution, damage reconciliation, invoicing, and payment — while leveraging ERPNext for financials/inventory and HRMS for staff scheduling.

## Dependencies

- Frappe Framework v15+
- ERPNext
- HRMS

## Installation

```bash
bench get-app https://github.com/puzzo-dev/event_bookings.git
bench --site your-site.local install-app event_bookings
```

After installation:
1. Open **Event Settings** and configure defaults (warehouse, cost center, shift type, COA accounts)
2. The installer seeds 5 default Event Types (Wedding, Corporate, Birthday, Conference, Private Party)
3. Event-specific Chart of Accounts entries (Event Revenue, Event COGS, Event Damage Expenses) are created per company

## Features

### DocTypes
- **Event Booking** — Central document tracking the full event lifecycle
- **Event Type** — Classification of events (seeded with defaults)
- **Event Settings** — Global defaults (warehouse, cost center, accounts, shift type, notifications)
- **Event Staff Requirement** — Child table: roles needed per event
- **Event Assigned Staff** — Child table: read-only view of assigned employees (auto-populated from Shift Assignments)

### Workflow
9-state workflow with role-based transitions:

```
New → Quoted → Negotiating → Confirmed → In Preparation → Executed → Invoiced → Paid
                                                                            ↘ Cancelled
```

Each state is gated by role (Sales User, Event Manager, Accounts User).

### Status Transition Automation
| Transition | Side Effect |
|---|---|
| → Confirmed | Auto-creates per-event Cost Center (if enabled) |
| → In Preparation | Creates Shift Assignments for staff requirements |
| → Invoiced | Auto-creates Sales Invoice from linked Sales Order |
| → Cancelled | Cancels linked Quotation, SO, SI, MR; releases Shift Assignments |

### ERPNext Integration
- **Quotation** — auto-linked via mapped doc + on_submit hook
- **Sales Order** — updates `total_actual` on submit
- **Sales Invoice** — auto-created on Invoiced transition, back-linked on submit
- **Stock Entry** — Material Issue for damage reconciliation (submitted)
- **Material Request** — linked for procurement planning
- Custom `event_booking` Link field added to all related ERPNext DocTypes (with `search_index`)

### HRMS Integration
- Shift Assignments created during "In Preparation" transition
- `assigned_staff` child table auto-populated from Shift Assignments
- Staff counts (`qty_assigned`) synced on Shift Assignment updates

### Purchase & Expense Tracking
- Link **Purchase Orders** and **Purchase Invoices** to Event Bookings via the `event_booking` field
- `total_purchase_cost` auto-accumulated from submitted Purchase Invoices
- Profitability report includes purchase costs in COGS calculation
- Dashboard connections show related POs and PIs on the Event Booking form

### Damage Reconciliation
- "Record Damages" dialog on Executed bookings
- Creates Material Issue Stock Entry (submitted) for inventory write-off
- Accumulates `damage_cost` on the booking

### Customer Portal
- `/my-bookings` page for customers to view their bookings
- Quote approval workflow via portal (uses `apply_workflow`)
- Paginated API with "Load More" support

### Dashboard & Reporting
- **Workspace** with 4 Number Cards and 3 Dashboard Charts
- **Event Booking Profitability** Script Report: revenue, COGS, damage, net profit, margin %
- **Calendar View** for visual event scheduling
- **Dashboard connections** showing linked Quotations, SOs, SIs, Stock Entries, Shift Assignments

### Scheduled Tasks
- **Daily**: Payment status sync (Invoiced→Paid), T-3/T-1 event reminders, unstaffed alerts
- All tasks wrapped in error handling — one failure won't block others

### Notifications
- Email reminders for upcoming events
- Unstaffed position alerts
- WhatsApp integration (via `publish_realtime`)
- Error-resilient: all sends wrapped in try/except with `frappe.log_error`

## Custom Roles
- **Event Manager** — Full access to Event Booking, Settings, Types
- **Event User** — Read-only access

## Print Format
- **Event Booking Confirmation** — Jinja template with booking details, SO line items, and staff requirements

## Testing

```bash
cd apps/event_bookings
python -m pytest event_bookings/tests/ -q
```

121 unit tests covering all modules. Tests use `unittest.mock` to mock `frappe` — no live Frappe site required.

## License

MIT
