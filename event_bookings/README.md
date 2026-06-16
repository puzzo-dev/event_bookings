# Event Bookings

**Version:** 0.0.1  
**License:** MIT  
**Publisher:** Avril Beetails  

A Frappe/ERPNext application for end-to-end event management — from initial inquiry through quotation, confirmation, execution, invoicing, and post-event review.

---

## Features

- **Event Booking Lifecycle** — Track events through a structured status pipeline: `New → Quoted → Negotiating → Confirmed → In Preparation → Executed → Invoiced → Paid → Cancelled`.
- **ERPNext Integration** — Seamlessly linked with Quotation, Sales Order, Sales Invoice, Stock Entry, and Material Request.
- **Profitability Reporting** — Built-in Event Booking Profitability report with revenue, COGS, and margin analysis (Redis-cached for performance).
- **Pipeline Dashboard** — Event Booking Pipeline report tracks upcoming events, days until event, and staffing requirements.
- **Staffing Alerts** — Automated daily scheduler alerts Event Managers when staff requirements are unmet.
- **Cost Center Automation** — Optional per-event Cost Center auto-creation when a booking is confirmed.
- **Booking Reviews** — Customer review submission API with rate limiting, duplicate prevention, and HTML sanitization.
- **Warehouse Workflow** — Dedicated Events Warehouse for Material Transfer and Material Issue tracking.
- **Custom Fields** — Event Booking link injected into Stock Entry, Sales Order, Sales Invoice, Purchase Invoice, Expense Claim, Journal Entry, Material Request, and Stock Reconciliation.
- **Accounting Dimension** — Event Booking registered as a first-class Accounting Dimension in ERPNext.

---

## Requirements

| Dependency | Version |
|------------|---------|
| Frappe Framework | v15+ |
| ERPNext | v15+ |
| HRMS | v15+ |

---

## Installation

Run from your bench root directory:

```bash
# Option 1: Install from local path (development)
cd /path/to/frappe-bench
bench get-app /path/to/event_bookings

# Option 2: Install from a Git repository
bench get-app https://github.com/your-org/event_bookings.git

# Install on a site
bench --site your-site.local install-app event_bookings

# Migrate schema and fixtures
bench --site your-site.local migrate
```

---

## Post-Install Setup

1. Open **Event Booking Settings** (Event Bookings module) and configure:
   - **Default Warehouse** — for Material Issue
   - **Events Warehouse** — for Material Transfer
   - **Default Cost Center** — required if *Auto-Create Cost Center per Event* is enabled
   - **Auto-Create Cost Center per Event** — toggles per-event cost center generation
   - **Require Review Before Invoicing** — enforces an approved Booking Review before status can move to *Invoiced*

2. Review seeded **Event Types** (Wedding, Corporate, Birthday, Conference, Private Party). Add or customize as needed.

3. Assign the **Event Manager** and **Event User** roles to appropriate users.

---

## Architecture

```
event_bookings/
├── event_bookings/
│   ├── doctype/
│   │   ├── event_booking/         # Core booking document
│   │   ├── event_booking_settings/  # Global configuration
│   │   ├── event_type/            # Event classification
│   │   ├── event_staff_requirement/ # Child table for staffing
│   │   └── booking_review/        # Post-event customer reviews
│   ├── report/
│   │   ├── event_booking_profitability/
│   │   └── event_booking_pipeline/
│   ├── workspace/
│   │   └── event_bookings.json    # Desk workspace with charts & shortcuts
│   ├── dashboard_chart/
│   │   ├── event_revenue_trend/
│   │   └── monthly_events/
│   └── print_format/
│       └── event_booking_confirmation/
├── utils/
│   ├── scheduler.py               # Daily scheduled tasks
│   ├── erpnext_hooks.py           # Doc event handlers for ERPNext docs
│   ├── seed.py                    # Default Event Types seeding
│   └── notifications.py           # WhatsApp placeholder
├── tests/                         # Unit & integration tests
├── fixtures/                      # Custom Field fixtures
├── patches/                       # Data migration patches
├── hooks.py                       # App hooks & doc_events
├── install.py                     # after_install seeding logic
└── README.md                      # This file
```

---

## Key Workflows

### Sales Flow
1. Create an **Event Booking** (status = `New`).
2. Click **Create Quotation** → generates a linked Quotation.
3. Upon Quotation submission, Event Booking auto-updates to `Quoted`.
4. Convert Quotation → Sales Order → Sales Invoice.
5. Event Booking auto-syncs linked documents and calculates totals.

### Inventory Flow
1. Create a **Stock Entry** of type `Material Transfer` or `Material Issue`.
2. Link it to the Event Booking via the `event_booking` custom field.
3. On submission, the Stock Entry is linked to the Event Booking.
4. On cancellation, the link is automatically cleared.

### Cost Center Flow (optional)
1. Enable **Auto-Create Cost Center per Event** in Event Booking Settings.
2. Set a **Default Cost Center** as the parent.
3. When an Event Booking moves to `Confirmed`, a child Cost Center is created.
4. The Cost Center is automatically used in linked Quotations and mapped documents.

### Review Flow
1. Event executes and moves to `Executed` / `Invoiced` / `Paid`.
2. Customer submits a review via the `submit_review` API.
3. If **Require Review Before Invoicing** is enabled, an approved review is mandatory before invoicing.

---

## Scheduler Tasks

Daily tasks are registered in `hooks.py` and run automatically:

| Task | Description |
|------|-------------|
| `sync_invoice_payment_status` | Moves `Invoiced` bookings to `Paid` when the linked Sales Invoice is paid |
| `send_pre_event_reminders` | Emails customers N days before their event (configurable) |
| `send_unstaffed_alerts` | Emails Event Managers about staffing shortfalls |
| `notify_managers_upcoming_events` | Posts Notification Logs for Event Managers about events in the next 7 days |

---

## REST API

The following methods are whitelisted for external/internal use:

| Method | Path | Purpose |
|--------|------|---------|
| `make_quotation` | `event_bookings.doctype.event_booking.event_booking.make_quotation` | Map Event Booking → Quotation |
| `make_project` | `event_bookings.doctype.event_booking.event_booking.make_project` | Map Event Booking → Project |
| `get_items_from_quotation` | `event_bookings.doctype.event_booking.event_booking.get_items_from_quotation` | Fetch quotation line items |
| `get_items_from_sales_order` | `event_bookings.doctype.event_booking.event_booking.get_items_from_sales_order` | Fetch SO line items |
| `submit_review` | `event_bookings.doctype.booking_review.booking_review.submit_review` | Submit a customer review |

All APIs require authentication (`allow_guest=False`).

---

## Running Tests

```bash
# Run all tests for this app
bench --site your-site.local run-tests --app event_bookings

# Run a specific test module
bench --site your-site.local run-tests --module event_bookings.tests.test_event_booking_unit

# Run a specific test class
bench --site your-site.local run-tests --module event_bookings.tests.test_scheduler_unit --test TestSendUnstaffedAlerts
```

---

## Troubleshooting

### Event Booking Settings missing
Run `bench --site your-site.local migrate` to sync fixtures and single doctypes.

### Custom Fields not appearing
Ensure `bench export-fixtures` was run after installation, then `bench migrate`.

### Scheduler not running
1. Enable the scheduler: `bench --site your-site.local enable-scheduler`
2. Ensure the `daily` job is registered in `hooks.py`.
3. Check `bench doctor` for worker health.

### Cost Center not auto-creating
Verify that:
1. `auto_create_cost_center_per_event` is checked in Event Booking Settings.
2. `default_cost_center` is populated.
3. The Event Booking status changed to `Confirmed` (not just set in the form before save).

---

## Development

### Adding a New DocType
```bash
bench --site your-site.local make-doc-type event_bookings "My New DocType"
```

### Exporting Fixtures
After making changes to Custom Fields, Roles, Workspaces, or Print Formats via the Desk UI:
```bash
bench --site your-site.local export-fixtures
```

### Building Assets
```bash
bench build --app event_bookings
```

---

## Changelog

### 0.0.1
- Initial release with full event lifecycle, ERPNext integration, profitability reports, and review system.

---

## Support

For issues or feature requests, please contact the publisher or open an issue in the project's repository.
