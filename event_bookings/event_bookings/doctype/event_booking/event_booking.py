import frappe
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils import today


class EventBooking(Document):
	def validate(self):
		self.validate_dates()

	def before_insert(self):
		self.set_defaults_from_settings()

	def before_save(self):
		if self.has_status_changed():
			self.handle_status_transition()

	# -----------------------------------------------------------------
	# Validations
	# -----------------------------------------------------------------

	def validate_dates(self):
		if self.event_date and self.event_date < today():
			if self.is_new():
				frappe.throw("Event Date cannot be in the past for new bookings.")

		if self.event_end_time and self.event_time and self.event_end_time <= self.event_time:
			frappe.throw("Event End Time must be after Event Time.")

	# -----------------------------------------------------------------
	# Defaults
	# -----------------------------------------------------------------

	def set_defaults_from_settings(self):
		settings = self.get_settings()
		if (
			not self.event_cost_center
			and settings.default_cost_center
			and not settings.auto_create_cost_center_per_event
		):
			self.event_cost_center = settings.default_cost_center

	def ensure_event_cost_center(self):
		settings = self.get_settings()
		if not settings.auto_create_cost_center_per_event:
			self.set_defaults_from_settings()
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

		if status == "Confirmed":
			self.ensure_event_cost_center()

		elif status == "In Preparation":
			self.create_shift_assignments()

		elif status == "Invoiced":
			self.create_sales_invoice()

		elif status == "Cancelled":
			self.handle_cancellation()

	# -----------------------------------------------------------------
	# Sales Invoice Creation
	# -----------------------------------------------------------------

	def create_sales_invoice(self):
		if self.sales_invoice:
			return

		if not self.sales_order:
			frappe.msgprint("No Sales Order linked — cannot auto-create Sales Invoice.")
			return

		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"customer": self.customer,
				"event_booking": self.name,
				"cost_center": self.event_cost_center,
				"items": [],
			}
		)

		so = frappe.get_doc("Sales Order", self.sales_order)
		for item in so.items:
			si.append(
				"items",
				{
					"item_code": item.item_code,
					"item_name": item.item_name,
					"qty": item.qty,
					"rate": item.rate,
					"amount": item.amount,
					"sales_order": self.sales_order,
					"so_detail": item.name,
					"cost_center": self.event_cost_center,
				},
			)

		si.insert(ignore_permissions=True)
		self.sales_invoice = si.name

	# -----------------------------------------------------------------
	# Cancellation
	# -----------------------------------------------------------------

	def handle_cancellation(self):
		self._cancel_linked_doc("Quotation", self.quotation)
		self._cancel_linked_doc("Sales Order", self.sales_order)
		self._cancel_linked_doc("Sales Invoice", self.sales_invoice)
		self._cancel_linked_doc("Material Request", self.material_request)
		self._release_shift_assignments()

	def _cancel_linked_doc(self, doctype, name):
		if not name:
			return
		try:
			doc = frappe.get_doc(doctype, name)
			if doc.docstatus == 1:
				doc.cancel()
		except Exception:
			frappe.log_error(
				f"Could not cancel {doctype} {name} for {self.name}",
				"Event Booking Cancellation",
			)

	def _release_shift_assignments(self):
		shifts = frappe.get_all(
			"Shift Assignment",
			filters={"event_booking": self.name, "docstatus": ("<", 2)},
			pluck="name",
		)
		for shift_name in shifts:
			try:
				shift = frappe.get_doc("Shift Assignment", shift_name)
				if shift.docstatus == 1:
					shift.cancel()
				elif shift.docstatus == 0:
					frappe.delete_doc("Shift Assignment", shift_name, force=True)
			except Exception:
				frappe.log_error(
					f"Could not release Shift Assignment {shift_name} for {self.name}",
					"Event Booking Cancellation",
				)

	# -----------------------------------------------------------------
	# Damage Reconciliation (Stock Entry write-offs)
	# -----------------------------------------------------------------

	def create_damage_stock_entry(self, items):
		"""Create a Stock Entry (Material Issue) to write off damaged items.

		Args:
		    items: list of dicts with keys: item_code, qty_damaged, rate (optional)
		"""
		settings = self.get_settings()
		warehouse = settings.damage_warehouse or settings.default_warehouse
		expense_account = settings.default_damage_account

		if not warehouse:
			frappe.throw("Set a Damage Warehouse or Default Warehouse in Event Settings.")

		se = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Issue",
				"event_booking": self.name,
				"items": [],
			}
		)

		total_damage = 0
		for item in items:
			qty = item.get("qty_damaged", 0)
			if qty <= 0:
				continue
			rate = item.get("rate") or frappe.db.get_value("Item", item["item_code"], "valuation_rate") or 0
			se.append(
				"items",
				{
					"item_code": item["item_code"],
					"qty": qty,
					"s_warehouse": warehouse,
					"basic_rate": rate,
					"expense_account": expense_account,
					"cost_center": self.event_cost_center,
				},
			)
			total_damage += qty * rate

		if not se.items:
			frappe.msgprint("No damaged items to write off.")
			return

		se.insert(ignore_permissions=True)
		se.submit()
		self.damage_cost = (self.damage_cost or 0) + total_damage

	# -----------------------------------------------------------------
	# Shift Assignments (HRMS Integration)
	# -----------------------------------------------------------------

	def create_shift_assignments(self):
		settings = self.get_settings()
		if not settings.default_shift_type:
			frappe.throw("Set a Default Shift Type in Event Settings before creating Shift Assignments.")

		failed = []
		for req in self.staff_requirements:
			needed = frappe.utils.flt(req.qty_required) - frappe.utils.flt(req.qty_assigned or 0)
			for _ in range(int(needed)):
				try:
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
				except Exception:
					failed.append(req.designation)
					frappe.log_error(title=f"Shift Assignment failed for {self.name} / {req.designation}")

		self.update_staff_assignment_counts()
		self._sync_assigned_staff()

		if failed:
			frappe.msgprint(
				f"Some Shift Assignments could not be created: {', '.join(failed)}. Check the Error Log.",
				indicator="orange",
				alert=True,
			)

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
		self._sync_assigned_staff()

	def _sync_assigned_staff(self):
		"""Populate the assigned_staff child table from linked Shift Assignments."""
		self.assigned_staff = []
		shifts = frappe.get_all(
			"Shift Assignment",
			filters={"event_booking": self.name, "docstatus": ("<", 2)},
			fields=["name", "employee", "employee_name", "designation", "start_date"],
		)
		for sa in shifts:
			self.append(
				"assigned_staff",
				{
					"employee": sa.employee,
					"employee_name": sa.employee_name,
					"designation": sa.designation,
					"shift_date": sa.start_date,
					"shift_assignment": sa.name,
				},
			)

	def recalculate_purchase_cost(self):
		"""Sum grand_total from all submitted Purchase Invoices linked to this booking."""
		total = frappe.db.get_value(
			"Purchase Invoice",
			filters={"event_booking": self.name, "docstatus": 1},
			fieldname="sum(grand_total)",
		)
		self.total_purchase_cost = total or 0

	# -----------------------------------------------------------------
	# Utilities
	# -----------------------------------------------------------------

	def get_settings(self):
		return frappe.get_cached_doc("Event Settings", "Event Settings")


@frappe.whitelist()
def record_damages(event_booking, items):
	import json

	if isinstance(items, str):
		items = json.loads(items)

	doc = frappe.get_doc("Event Booking", event_booking)
	frappe.has_permission("Event Booking", "write", doc=doc, throw=True)
	doc.create_damage_stock_entry(items)
	doc.save(ignore_permissions=True)


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
					"event_cost_center": "cost_center",
				},
			}
		},
		target_doc,
		set_missing_values,
	)

	return doclist
