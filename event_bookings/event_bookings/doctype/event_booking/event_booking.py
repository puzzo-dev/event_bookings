import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


class EventBooking(Document):
    def validate(self):
        self.validate_dates()
        self.calculate_totals()
        self.calculate_breakage()

    def before_insert(self):
        self.set_defaults_from_settings()
        self.set_cost_center()

    def on_update(self):
        if self.has_status_changed():
            self.handle_status_transition()

    # -----------------------------------------------------------------
    # Validations
    # -----------------------------------------------------------------

    def validate_dates(self):
        if self.event_date and self.event_date < today():
            if self.is_new():
                frappe.throw("Event Date cannot be in the past for new bookings.")

    def calculate_totals(self):
        estimated = 0.0
        for item in self.services:
            item.amount = flt(item.qty) * flt(item.rate)
            estimated += flt(item.amount)
        self.total_estimated = estimated

    def calculate_breakage(self):
        breakage = 0.0
        settings = self.get_settings()
        for item in self.services:
            if item.is_stock_item and item.qty_broken:
                rate = flt(item.rate) or 1
                breakage += flt(item.qty_broken) * rate
        self.breakage_cost = breakage

    # -----------------------------------------------------------------
    # Defaults
    # -----------------------------------------------------------------

    def set_defaults_from_settings(self):
        settings = self.get_settings()
        if not self.event_cost_center and settings.default_cost_center:
            self.event_cost_center = settings.default_cost_center

    def set_cost_center(self):
        settings = self.get_settings()
        if not self.event_cost_center and settings.default_cost_center:
            self.event_cost_center = settings.default_cost_center

    def ensure_event_cost_center(self):
        settings = self.get_settings()
        if not settings.auto_create_cost_center_per_event:
            self.set_cost_center()
            return

        if self.event_cost_center:
            return

        parent_cc = settings.default_cost_center
        if not parent_cc:
            frappe.throw("Set a Default Cost Center in Event Settings to auto-create per-event cost centers.")

        cc_name = f"{self.name} - {self.event_name}"
        if not frappe.db.exists("Cost Center", cc_name):
            cc = frappe.get_doc(
                {
                    "doctype": "Cost Center",
                    "cost_center_name": cc_name,
                    "parent_cost_center": parent_cc,
                    "is_event_cost_center": 1,
                    "company": self.get_company_from_cost_center(parent_cc),
                }
            )
            cc.insert(ignore_permissions=True)

        self.event_cost_center = cc_name

    def get_company_from_cost_center(self, cost_center):
        return frappe.db.get_value("Cost Center", cost_center, "company") or frappe.defaults.get_defaults().get("company")

    # -----------------------------------------------------------------
    # Status Transition Hook
    # -----------------------------------------------------------------

    def has_status_changed(self):
        if self.is_new():
            return False
        old = frappe.db.get_value("Event Booking", self.name, "booking_status")
        return old != self.booking_status

    def handle_status_transition(self):
        status = self.booking_status

        if status == "Quoted":
            self.create_quotation()

        elif status == "Confirmed":
            self.ensure_event_cost_center()

        elif status == "In Preparation":
            self.create_material_request()
            self.create_shift_assignments()

        elif status == "Executed":
            pass  # Validation prevents service edits

        elif status == "Invoiced":
            pass  # Sales Manager creates invoice manually or via auto-create

        elif status == "Paid":
            pass  # Set by scheduler when SI is paid

    # -----------------------------------------------------------------
    # Quotation Builder
    # -----------------------------------------------------------------

    def create_quotation(self):
        if self.quotation:
            return

        settings = self.get_settings()
        qt = frappe.get_doc(
            {
                "doctype": "Quotation",
                "quotation_to": "Customer",
                "party_name": self.customer,
                "event_booking": self.name,
                "cost_center": self.event_cost_center or settings.default_cost_center,
            }
        )

        for svc in self.services:
            qt.append(
                "items",
                {
                    "item_code": svc.item,
                    "qty": svc.qty,
                    "rate": svc.rate,
                    "cost_center": self.event_cost_center or settings.default_cost_center,
                    "income_account": settings.default_income_account,
                },
            )

        qt.insert(ignore_permissions=True)
        self.quotation = qt.name

    # -----------------------------------------------------------------
    # Material Request
    # -----------------------------------------------------------------

    def create_material_request(self):
        if self.material_request:
            return

        settings = self.get_settings()
        stock_items = [s for s in self.services if s.is_stock_item]
        if not stock_items:
            return

        mr = frappe.get_doc(
            {
                "doctype": "Material Request",
                "material_request_type": "Material Issue",
                "event_booking": self.name,
                "cost_center": self.event_cost_center or settings.default_cost_center,
            }
        )

        for svc in stock_items:
            mr.append(
                "items",
                {
                    "item_code": svc.item,
                    "qty": svc.qty,
                    "warehouse": settings.default_warehouse,
                    "cost_center": self.event_cost_center or settings.default_cost_center,
                },
            )

        mr.insert(ignore_permissions=True)
        self.material_request = mr.name

    # -----------------------------------------------------------------
    # Shift Assignments (HRMS Integration)
    # -----------------------------------------------------------------

    def create_shift_assignments(self):
        settings = self.get_settings()
        for req in self.staff_requirements:
            needed = flt(req.qty_required) - flt(req.qty_assigned or 0)
            for _ in range(int(needed)):
                shift = frappe.get_doc(
                    {
                        "doctype": "Shift Assignment",
                        "employee": None,
                        "designation": req.designation,
                        "shift_type": settings.default_shift_type,
                        "date": self.event_date,
                        "status": "Planned",
                        "event_booking": self.name,
                    }
                )
                shift.insert(ignore_permissions=True)
        self.update_staff_assignment_counts()

    def update_staff_assignment_counts(self):
        for req in self.staff_requirements:
            count = frappe.db.count(
                "Shift Assignment",
                filters={
                    "event_booking": self.name,
                    "designation": req.designation,
                    "docstatus": ("<", 2),
                },
            )
            req.qty_assigned = count

    # -----------------------------------------------------------------
    # Utilities
    # -----------------------------------------------------------------

    def get_settings(self):
        return frappe.get_cached_doc("Event Settings", "Event Settings")
