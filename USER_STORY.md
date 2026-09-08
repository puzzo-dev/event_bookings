# Events Management — User Story & Workflow Trace

## Overview

A corporate event management company uses ERPNext + Events Management to handle the full lifecycle from first client inquiry through post-event review and payment reconciliation.

---

## Actors

| Actor | Role |
|---|---|
| **Event Manager** | Full control — creates bookings, manages pipeline, approves reviews |
| **Event Assistant** | Read-only access to bookings |
| **Sales Manager / Sales User** | Creates and manages Quotations, Sales Orders, Invoices |
| **Accounts User** | Reads and processes invoices |
| **Customer / Lead** | External — submits post-event review via API |

---

## End-to-End Workflow

### 1. Inquiry → New Booking

A prospect calls about hosting a wedding reception for 150 guests on August 15.

**Actor:** Event Manager  
**Action:** Opens *Event Bookings* workspace → *New Event Booking* shortcut.

Fills in:
- **Event Name:** "Ahmed & Fatima Wedding"
- **Booking Date:** today (auto-defaults)
- **Party Type:** Customer → **Party Name:** Acme Weddings Ltd
- **Event Type:** Wedding
- **Event Date:** 2026-08-15, **Time:** 17:00, **End Time:** 23:00
- **Guest Count:** 150
- **Event Location:** Grand Ballroom, Victoria Island
- **Special Requirements:** Halal catering, no alcohol

Status auto-defaults to **New**.

---

### 2. Quotation Sent → Status: Quoted

The event manager discusses package options and is ready to send a price proposal.

**Actor:** Event Manager  
**Action:** Changes `Booking Status` → **Quoted** and saves.

**System behaviour (automatic):**
- `before_save` detects status change New → Quoted
- `handle_status_transition()` calls `create_quotation()`
- A Frappe/ERPNext **Quotation** is created and linked to the booking (`quotation` field populated)
- The Sales team is now notified to add line items to the Quotation
- `total_estimated` is recalculated from Quotation line items via SQL aggregation
- Google Calendar event is pushed (if `sync_with_google_calendar` is enabled)

**Notification:** "Event Pre-Event Reminder" Frappe Notifications (3 days and 1 day before) are set to fire via scheduler.

---

### 3. Negotiation → Status: Negotiating

The client requests changes to the catering package.

**Actor:** Sales Manager  
**Action:** Updates Quotation items in ERPNext. Changes booking status → **Negotiating**.

**System behaviour:**
- `on_update` hook on Quotation fires → `on_quotation_update()` recalculates `total_estimated` on the Event Booking via `recalculate_totals()` (targeted `db_set`, no full save)
- Status machine validates the transition: Quoted → Negotiating is allowed

---

### 4. Booking Confirmed → Status: Confirmed

Client accepts the quote.

**Actor:** Event Manager  
**Action:** Submits the Quotation in ERPNext (Sales team flow). Quotation `on_submit` hook fires → `on_quotation_submit()` updates `status` to **Confirmed** on the linked Event Booking.

**System behaviour (automatic):**
- `handle_status_transition()` calls `ensure_event_cost_center()`
- If `auto_create_cost_center_per_event` is enabled in Event Settings, a dedicated Cost Center `EVT-2026-0001 - Ahmed & Fatima Wedding - ABC` is created under the default parent
- The Cost Center is linked to the booking for accurate P&L tracking per event

---

### 5. In Preparation → Status: In Preparation

Event is 3 weeks away. Logistics begin.

**Actor:** Event Manager  
**Action:** Changes status → **In Preparation**.

**System behaviour (automatic):**
- `_notify_staff_requirements()` inspects the **Staff Requirements** child table
- If any designation has `qty_required > qty_assigned`, a warning dialog lists the gaps
- e.g., "Waiter: 5 slot(s) required, Chef: 2 slot(s) required"
- HR Managers create **Shift Assignments** in ERPNext HR module with `event_booking = EVT-2026-0001`
- When Shift Assignments are saved, `on_shift_assignment_update()` increments `qty_assigned` on the matching `Event Staff Requirement` row

**Scheduled (daily):**
- `send_unstaffed_alerts()` queries Confirmed bookings where `qty_assigned < qty_required` and emails Event Managers a single grouped digest — a per-document Frappe Notification cannot aggregate across bookings, which is why this one stays in the scheduler

---

### 6. Event Day → Status: Executed

The event runs. Staff collect consumables from the warehouse (ERPNext Stock Entry — Material Issue against `event_booking`).

**Actor:** Event Manager  
**Action:** Changes status → **Executed**.

**System behaviour:**
- Sales team creates Sales Order from the Quotation in ERPNext
- `on_submit` of Sales Order → `on_sales_order_submit()` sets `status = Invoiced` on the Event Booking and updates `sales_order` link
- `total_actual` recalculated from Sales Order line items

---

### 7. Invoiced → Status: Invoiced

**Actor:** Accounts User  
**Action:** Creates Sales Invoice from Sales Order.

**System behaviour:**
- `on_submit` of Sales Invoice → `on_sales_invoice_submit()` updates `sales_invoice` link on the booking
- `total_actual` recalculated from Sales Invoice amounts

---

### 8. Payment Received → Status: Paid

**Scheduled (daily — automatic):**
- `sync_invoice_payment_status()` runs a single SQL UPDATE JOIN:
  - Finds all `Invoiced` Event Bookings where the linked Sales Invoice `status = 'Paid'`
  - Sets `status = 'Paid'` in bulk, no full controller chain needed

No manual action required.

---

### 9. Post-Event Review

Three days after the event, the customer receives a satisfaction survey link.

**Actor:** Customer (external)  
**Action:** Submits a star rating and review text via the `submit_review` API endpoint.

**System behaviour:**
- Endpoint validates:
  - Booking status is in {Executed, Invoiced, Paid}
  - Caller is linked to the Customer (Contact.user, Customer.user, or staff with write permission)
  - Rate limit: max 3 submissions per hour (Redis)
  - Duplicate: no review within past 24 hours for same customer+event
  - review_text sanitized via `sanitize_html`, max 5000 chars
  - Rating 1–5
- A **Booking Review** document is created (status: Submitted)
- Event Manager reviews and sets status to **Approved** / **Rejected**; `is_published` flag controls customer-facing display

---

### 10. Cancellation (any stage)

**Actor:** Event Manager  
**Action:** Changes status → **Cancelled**.

**System behaviour:**
- `cancel_linked_documents()` enqueues a background job
- Background worker cancels (in order): Quotation → Sales Order → Sales Invoice, then all linked Stock Entries and Shift Assignments
- Each cancellation is permission-checked and individually error-logged on failure

---

## Financial Traceability

```
Event Booking
  └── Cost Center (per-event P&L)
  └── Quotation          → total_estimated
  └── Sales Order        → total_actual (preferred)
  └── Sales Invoice      → total_actual (fallback)
  └── Material Request   → purchasing view
  └── Stock Entry (Material Issue) → COGS (profitability report)
  └── Stock Reconciliation write-downs → Damages / Losses (profitability report)
```

Profitability per event = **Revenue** (actual or estimated) − **COGS** − **Damages**

---

## Status Machine

```
New → Quoted → Invoiced → Confirmed → Paid → Executed
 └────────────────────────────────────────────────────→ Cancelled
```

Every transition is validated by `VALID_STATUS_TRANSITIONS`. Forward-only; no backward moves (except Cancelled from any state).

---

## Key Integrations

| Integration | Trigger | Effect |
|---|---|---|
| Google Calendar | `on_update` | Creates/updates/deletes calendar event (background job) |
| ERPNext Quotation | Status → Quoted | Auto-creates Quotation |
| ERPNext Sales Order | SO submitted | Sets status → Invoiced, updates `total_actual` |
| ERPNext Sales Invoice | SI submitted | Captures final revenue |
| ERPNext Stock Entry | SO submitted | Material Request also created for procurement |
| HRMS Shift Assignment | HR save | Updates `qty_assigned` on staff requirement rows |
| Frappe Scheduler (daily) | Cron | Syncs payment status, sends under-staffed alerts |
