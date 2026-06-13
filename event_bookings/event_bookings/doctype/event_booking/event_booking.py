import frappe
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils import today

class EventBooking(Document):
    def validate(self):
        self.validate_dates()

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

    # -----------------------------------------------------------------
    # Defaults
    # -----------------------------------------------------------------

    def set_defaults_from_settings(self):
        settings = self.get_settings()
        if not self.event_cost_center and settings.default_cost_center and not settings.auto_create_cost_center_per_event:
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

        if status == "Confirmed":
            self.ensure_event_cost_center()

        elif status == "In Preparation":
            self.create_shift_assignments()

    # -----------------------------------------------------------------
    # Shift Assignments (HRMS Integration)
    # -----------------------------------------------------------------

    def create_shift_assignments(self):
        settings = self.get_settings()
        for req in self.staff_requirements:
            needed = frappe.utils.flt(req.qty_required) - frappe.utils.flt(req.qty_assigned or 0)
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

@frappe.whitelist()
def make_quotation(source_name, target_doc=None):
    def set_missing_values(source, target):
        target.quotation_to = "Customer"
        target.event_booking = source.name

    doclist = get_mapped_doc(
        "Event Booking",
        source_name,
        {
            "Event Booking": {
                "doctype": "Quotation",
                "field_map": {
                    "customer": "party_name",
                    "contact_person": "contact_person",
                    "event_cost_center": "cost_center"
                }
            }
        },
        target_doc,
        set_missing_values
    )

    return doclist
