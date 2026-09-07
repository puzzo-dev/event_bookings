# Event Booking — Standard Operating Procedures (SOP)

This document describes the end-to-end workflow for planning, executing, and closing an event using the **Events Management** module.

---

## Pre-Event Phase

### 1. Create Event Type (one-time setup)
- Navigate to **Events Management > Event Type > New**.
- Define the category (e.g., Wedding, Corporate Gala, Birthday, Concert).
- Set default pricing markup or notes if applicable.
- Save.

### 2. Create the Event Booking
- Navigate to **Events Management > Event Booking > New**.
- Fill in the **Client & Event Core** section:
  - **Event Name**: descriptive name for internal reference.
  - **Customer**: select existing Customer or create new.
  - **Contact Person**: link to the customer's primary contact.
  - **Event Type**: select from step 1.
  - **Event Planner** (optional): assign a Sales Partner.
  - **Booking Date & Time**: when the booking was confirmed.
- Fill in **Logistics & Schedule**:
  - **Event Timing**: start date/time of the actual event.
  - **Event End Date & Time**: when the event concludes.
  - **Guest Count**: expected attendance.
  - **Event Location**: venue address or name.
- Fill in **Special Requirements**:
  - Catering notes, AV requirements, accessibility, décor, etc.
- Save as **Draft**.

### 3. Generate Quotation
- Open the Event Booking.
- Click **Actions > Create Quotation**.
- The system generates a Quotation linked to this Event Booking.
- Add line items (venue rental, catering, staff, equipment).
- Submit Quotation to customer.
- **Status update**: manually update Booking Status to **Quoted**.

### 4. Customer Approval & Negotiation
- If customer requests changes, amend the Quotation or create a revised one.
- Once approved, convert Quotation to **Sales Order**.
- The linked Sales Order auto-populates on the Event Booking.
- **Status update**: booking advances automatically — Quoted → Invoiced (when SI submitted) → Confirmed (partly paid) → Paid (fully paid).

### 5. Project & Cost Center Setup (optional)
- If **Event Booking Settings** has "Auto-Create Cost Center Per Event" enabled, a Cost Center is auto-created on confirmation.
- Otherwise, manually create a Cost Center for this event.
- Link the Cost Center and optionally a **Project** to the Event Booking.
- Use the Project to track tasks, timelines, and milestones.

### 6. Staffing Plan
- In the Event Booking, scroll to **Staffing**.
- Add **Event Staff Requirement** rows:
  - Designation (Waiter, Security, MC, DJ, etc.).
  - Quantity required.
- These requirements are reference data for the HR team to plan shift assignments separately (HRMS).

### 7. Procurement & Inventory
- Create **Material Request** from the Event Booking (if items need purchasing).
- **Create Stock Entry from Event Booking**: Use the **Create → Stock Entry** button on the Event Booking form. A dialog lets you choose the Stock Entry type (Material Issue / Material Transfer / Material Transfer for Manufacture). The Stock Entry is prefilled with the Event Booking link, company, cost center, and the default warehouse from Event Booking Settings.
- **Stock Entry — Material Transfer**: Move stock items from the **Default Warehouse** to the **Events Warehouse** before the event starts.
- **During the Event**: Items reside in the **Events Warehouse** while the event is active.
- **Stock Entry — Material Transfer (Return)**: After the event, move good-condition items back from the **Events Warehouse** to the **Default Warehouse**.
- **Stock Entry — Material Issue**: Move damaged items from the **Events Warehouse** to the **Damages Warehouse**.
- All Stock Entries linked to the Event Booking are visible in the **Connections** tab on the Event Booking form.
- For items that get damaged during the event, use **Stock Reconciliation** after the event:
  - Create a Stock Reconciliation.
  - Set **Event Booking** field to link write-offs to this event.
  - Record damaged/broken items with current vs actual quantities.
- **Cancelling an Event Booking** automatically cancels all submitted linked Stock Entries (and Quotations, Sales Orders, Sales Invoices).

### 8. Pre-Event Financials
- Track deposits via **Journal Entry** or **Payment Entry**.
- Link all financial transactions to the Event Booking via the **Event Booking** accounting dimension (available on Journal Entry, Sales Invoice, Purchase Invoice, etc.).

---

## Post-Event Phase

### 1. Event Execution Confirmation
- Once the event is completed, update Booking Status to **Executed**.

### 2. Final Billing
- Create **Sales Invoice** from the Sales Order or directly.
- Add any post-event charges (damages, overtime, extra guests).
- The **Total Actual** field on Event Booking auto-updates from the Sales Invoice grand total.
- Send invoice to customer.
- Record payment via **Payment Entry**.

### 3. Stock Reconciliation (Damages)
- Navigate to **Stock > Stock Reconciliation > New**.
- Select the warehouse used for the event.
- Add items that were damaged or lost.
  - **Current Qty**: quantity before reconciliation.
  - **Qty**: reduced quantity (damaged items).
  - **Valuation Rate**: cost per unit.
- In the **Event Booking** field, select this event.
- Submit. The system calculates: `(current_qty - qty) × valuation_rate` as damages cost.

### 4. Expense Claims
- Staff or vendors submit **Expense Claim** documents.
- Link each claim to the Event Booking via the accounting dimension.

### 5. Profitability Analysis
- Navigate to **Events Management > Reports > Event Booking Profitability**.
- Filter by event name or date range.
- Review:
  - **Revenue**: from Sales Invoice (or Quotation if not yet invoiced).
  - **COGS**: linked purchase costs.
  - **Damages Cost**: from Stock Reconciliation write-downs.
  - **Net Profit** and **Margin %**.

### 6. Booking Review
- Create a **Booking Review** document.
- Rate the event execution, customer satisfaction, vendor performance.
- Link it back to the Event Booking.

### 7. Close the Event
- Update Booking Status to **Invoiced** → **Paid**.
- Archive the Event Booking. All linked documents (Quotation, Sales Order, Sales Invoice, Stock Reconciliation, Journal Entries, Expense Claims) remain queryable via the Connections tab.

---

## Key Linked Documents Summary

| Document | When to Create | Auto-linked? |
|----------|---------------|-------------|
| Quotation | Pre-event pricing | Yes (via Create Quotation) |
| Sales Order | Customer confirms booking | Manual conversion |
| Sales Invoice | Final billing | Manual |
| Material Request | Procurement needed | Manual |
| Stock Entry | Inventory movement | Manual |
| Stock Reconciliation | Post-event damage audit | Manual (Event Booking field) |
| Journal Entry | Deposits, transfers | Manual (Event Booking dimension) |
| Expense Claim | Staff/vendor reimbursements | Manual (Event Booking dimension) |
| Project | Task tracking | Manual / Auto (settings) |
| Cost Center | Budget tracking | Manual / Auto (settings) |
| Booking Review | Post-event feedback | Manual |

---

## Reports & Analytics

- **Event Booking Profitability**: per-event P&L with damages.
- **Event Booking Pipeline**: status funnel and revenue forecast.
- **Stock Reconciliation by Event**: filter by Event Booking to see all damage write-offs.
- **General Ledger by Event Booking**: use the Event Booking accounting dimension in financial reports.
