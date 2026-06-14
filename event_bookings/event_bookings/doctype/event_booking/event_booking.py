import frappe
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils import today, getdate


class EventBooking(Document):
	def validate(self):
		self.validate_dates()
		self.calculate_totals()

	def before_insert(self):
		self.set_defaults_from_settings()

	def before_save(self):
		if self.has_status_changed():
			self._validate_status_transition()
			self.handle_status_transition()

	VALID_STATUS_TRANSITIONS = {
		"New": {"Quoted", "Cancelled"},
		"Quoted": {"Negotiating", "Cancelled"},
		"Negotiating": {"Confirmed", "Cancelled"},
		"Confirmed": {"In Preparation", "Cancelled"},
		"In Preparation": {"Executed", "Cancelled"},
		"Executed": {"Invoiced", "Cancelled"},
		"Invoiced": {"Paid", "Cancelled"},
		"Paid": {"Cancelled"},
		"Cancelled": set(),
	}

	def _validate_status_transition(self):
		if self.is_new():
			return
		old_status = frappe.db.get_value("Event Booking", self.name, "booking_status")
		if old_status == self.booking_status:
			return
		allowed = self.VALID_STATUS_TRANSITIONS.get(old_status, set())
		if self.booking_status not in allowed:
			frappe.throw(
				f"Invalid status transition: '{old_status}' → '{self.booking_status}'. "
				f"Allowed transitions from '{old_status}': {', '.join(allowed) or 'none'}."
			)

	def on_update(self):
		pass

	# -----------------------------------------------------------------
	# Validations
	# -----------------------------------------------------------------

	def calculate_totals(self):
		self.total_estimated = self._get_doc_total("Quotation", self.quotation, "grand_total")
		self.total_actual = self._get_doc_total("Sales Order", self.sales_order, "grand_total")
		if not self.total_actual and self.sales_invoice:
			self.total_actual = self._get_doc_total("Sales Invoice", self.sales_invoice, "grand_total")

	def _get_doc_total(self, doctype, name, total_field):
		if not name:
			return 0.0
		try:
			return frappe.db.get_value(doctype, name, total_field) or 0.0
		except Exception:
			return 0.0

	def validate_dates(self):
		if self.event_date and getdate(self.event_date) < getdate(today()):
			if self.is_new():
				frappe.throw("Event Date cannot be in the past for new bookings.")

	# -----------------------------------------------------------------
	# Defaults
	# -----------------------------------------------------------------

	def set_cost_center(self):
		settings = self.get_settings()
		if not self.event_cost_center and settings.default_cost_center:
			self.event_cost_center = settings.default_cost_center

	def set_defaults_from_settings(self):
		settings = self.get_settings()
		if (
			not self.event_cost_center
			and settings.default_cost_center
			and not settings.auto_create_cost_center_per_event
		):
			self.event_cost_center = settings.default_cost_center

	def get_cost_center(self):
		"""Return the event's cost center, falling back to the default from Event Settings."""
		if self.event_cost_center:
			return self.event_cost_center
		return self.get_settings().default_cost_center

	def ensure_event_cost_center(self):
		settings = self.get_settings()
		if not settings.auto_create_cost_center_per_event:
			if not self.event_cost_center and settings.default_cost_center:
				self.event_cost_center = settings.default_cost_center
			return

		if self.event_cost_center:
			return

		parent_cc = settings.default_cost_center
		if not parent_cc:
			frappe.throw("Set a Default Cost Center in Event Settings to auto-create per-event cost centers.")

		cc_name = f"{self.name} - {self.event_name}"
		company = self.get_company_from_cost_center(parent_cc)
		abbr = frappe.db.get_value("Company", company, "abbr")
		full_cc_name = f"{cc_name} - {abbr}"

		if not frappe.db.exists("Cost Center", full_cc_name):
			if not frappe.has_permission("Cost Center", "create"):
				frappe.throw("You do not have permission to create a Cost Center.")
			cc = frappe.get_doc(
				{
					"doctype": "Cost Center",
					"cost_center_name": cc_name,
					"parent_cost_center": parent_cc,
					"is_event_cost_center": 1,
					"company": company,
				}
			)
			cc.insert(ignore_permissions=True)
			full_cc_name = cc.name

		self.event_cost_center = full_cc_name

	def get_company_from_cost_center(self, cost_center):
		return frappe.db.get_value(
			"Cost Center", cost_center, "company"
		) or frappe.defaults.get_defaults().get("company")

	# -----------------------------------------------------------------
	# Status Transition Hook
	# -----------------------------------------------------------------

	def has_status_changed(self):
		if self.is_new():
			return False
		old_status = frappe.db.get_value("Event Booking", self.name, "booking_status")
		return old_status != self.booking_status

	def handle_status_transition(self):
		status = self.booking_status

		if status == "Quoted":
			self.create_quotation()

		elif status == "Confirmed":
			self.ensure_event_cost_center()

		elif status == "In Preparation":
			self.create_shift_assignments()

	# -----------------------------------------------------------------
	# Document Creation Helpers
	# -----------------------------------------------------------------

	def create_quotation(self):
		if self.quotation:
			return
		settings = self.get_settings()
		qt = frappe.get_doc({
			"doctype": "Quotation",
			"quotation_to": "Customer",
			"party_name": self.customer,
			"event_booking": self.name,
			"cost_center": self.event_cost_center or settings.default_cost_center,
		})
		if not frappe.has_permission("Quotation", "create"):
			frappe.throw("You do not have permission to create a Quotation.")
		qt.insert(ignore_permissions=True)
		self.quotation = qt.name

	# -----------------------------------------------------------------
	# Shift Assignments (HRMS Integration)
	# -----------------------------------------------------------------

	def create_shift_assignments(self):
		settings = self.get_settings()
		if not settings.default_shift_type:
			frappe.throw("Set a Default Shift Type in Event Settings before creating Shift Assignments.")

		failed = []
		for req in self.get("staff_requirements") or []:
			needed = int(req.get("qty_required") or 0) - int(req.get("qty_assigned") or 0)
			for _ in range(max(0, needed)):
				try:
					shift = frappe.get_doc(
						{
							"doctype": "Shift Assignment",
							"employee": None,
							"designation": req.get("designation"),
							"shift_type": settings.default_shift_type,
							"date": self.event_date,
							"status": "Planned",
							"event_booking": self.name,
						}
					)
					if not frappe.has_permission("Shift Assignment", "create"):
						frappe.throw("You do not have permission to create a Shift Assignment.")
					shift.insert(ignore_permissions=True)
				except Exception:
					failed.append(req.get("designation"))
					frappe.log_error(title=f"Shift Assignment failed for {self.name} / {req.get('designation')}")

		self.update_staff_assignment_counts()

		if failed:
			frappe.msgprint(
				f"Some Shift Assignments could not be created: {', '.join(failed)}. Check the Error Log.",
				indicator="orange",
				alert=True,
			)

	def update_staff_assignment_counts(self):
		rows = frappe.db.sql(
			"""
			SELECT designation, COUNT(*) as cnt
			FROM `tabShift Assignment`
			WHERE event_booking = %s AND docstatus < 2
			GROUP BY designation
			""",
			self.name,
			as_dict=True,
		)
		counts = {r.get("designation"): r.get("cnt") for r in rows}
		for req in self.get("staff_requirements") or []:
			count = counts.get(req.get("designation"), 0)
			if isinstance(req, dict):
				req["qty_assigned"] = count
			else:
				req.qty_assigned = count

	# -----------------------------------------------------------------
	# Utilities
	# -----------------------------------------------------------------

	def get_settings(self):
		return frappe.get_cached_doc("Event Settings", "Event Settings")


@frappe.whitelist()
def make_quotation(source_name, target_doc=None):
	if not frappe.has_permission("Event Booking", "read", source_name):
		frappe.throw("You do not have permission to read this Event Booking.")

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
					"event_cost_center": "cost_center",
				},
			}
		},
		target_doc,
		set_missing_values,
	)

	return doclist

@frappe.whitelist()
def make_project(source_name, target_doc=None):
	if not frappe.has_permission("Event Booking", "read", source_name):
		frappe.throw("You do not have permission to read this Event Booking.")

	def set_missing_values(source, target):
		target.project_name = source.event_name or source.name
		target.customer = source.customer
		target.expected_start_date = source.booking_date or source.event_date
		target.expected_end_date = source.event_date

	doclist = get_mapped_doc(
		"Event Booking",
		source_name,
		{
			"Event Booking": {
				"doctype": "Project",
				"field_map": {
					"event_cost_center": "cost_center",
				},
			}
		},
		target_doc,
		set_missing_values,
	)

	return doclist


@frappe.whitelist()
def get_items_from_quotation(quotation_name):
	if not quotation_name:
		return []
	qt = frappe.get_doc("Quotation", quotation_name)
	return [
		{
			"item_code": item.item_code,
			"item_name": item.item_name,
			"qty": item.qty,
			"uom": item.uom,
			"rate": item.rate,
			"amount": item.amount,
		}
		for item in qt.items
	]


@frappe.whitelist()
def get_items_from_sales_order(sales_order_name):
	if not sales_order_name:
		return []
	so = frappe.get_doc("Sales Order", sales_order_name)
	return [
		{
			"item_code": item.item_code,
			"item_name": item.item_name,
			"qty": item.qty,
			"uom": item.uom,
			"rate": item.rate,
			"amount": item.amount,
		}
		for item in so.items
	]
