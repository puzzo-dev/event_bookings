import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils import today, getdate, flt, get_datetime, now_datetime


class EventBooking(Document):
	def validate(self):
		self._sync_datetime_fields()
		self.validate_dates()
		if self._linked_docs_changed():
			self.calculate_totals()
		if self.booking_status == "Invoiced":
			self.validate_review_requirement()

	def before_save(self):
		self._auto_create_event_cost_center()

	def _linked_docs_changed(self):
		"""Return True if any linked document field has changed from previous save."""
		previous = self.get_doc_before_save()
		if not previous:
			return True
		linked_fields = ("quotation", "sales_order", "sales_invoice", "stock_entry", "material_request")
		return any(getattr(self, f) != getattr(previous, f) for f in linked_fields)

	# -----------------------------------------------------------------
	# Validations
	# -----------------------------------------------------------------

	def calculate_totals(self):
		self.total_estimated = self._get_doc_total("Quotation", self.quotation, "grand_total")
		self.total_actual = self._get_doc_total("Sales Order", self.sales_order, "grand_total")
		if not self.total_actual and self.sales_invoice:
			self.total_actual = self._get_doc_total("Sales Invoice", self.sales_invoice, "grand_total")
		# Calculate planner commission from Sales Partner rate
		if self.event_planner:
			commission_rate = frappe.db.get_value("Sales Partner", self.event_planner, "commission_rate") or 0
			if commission_rate:
				base = self.total_actual or self.total_estimated or 0
				self.event_planner_commission_amount = base * (commission_rate / 100)

	def _get_doc_total(self, doctype, name, total_field):
		if not name:
			return 0.0
		try:
			return frappe.db.get_value(doctype, name, total_field) or 0.0
		except frappe.DatabaseError:
			return 0.0

	def validate_dates(self):
		if self.event_timing and get_datetime(self.event_timing) < now_datetime():
			if self.is_new():
				frappe.throw(_("Event Date and Time cannot be in the past for new bookings."))
		if self.event_end_datetime and self.event_timing:
			if get_datetime(self.event_end_datetime) <= get_datetime(self.event_timing):
				frappe.throw(_("Event End Time must be after Event Timing."))
		if self.event_end_date and self.event_date:
			if getdate(self.event_end_date) < getdate(self.event_date):
				frappe.throw(_("Event End Date must be on or after Event Date."))
			elif self.event_end_date == self.event_date and self.event_end_time and self.event_time:
				if self.event_end_time <= self.event_time:
					frappe.throw(_("Event End Time must be after Event Time."))

	def _sync_datetime_fields(self):
		"""Combine separate Date + Time fields into hidden Datetime fields for backward compatibility."""
		from datetime import datetime, time as dt_time
		from frappe.utils import getdate

		def _to_time(t):
			if isinstance(t, str):
				hour, minute, second = map(int, t.split(":"))
				return dt_time(hour, minute, second)
			return t or dt_time(0, 0, 0)

		if self.event_date and self.event_time:
			self.event_timing = datetime.combine(getdate(self.event_date), _to_time(self.event_time))
		elif self.event_date:
			self.event_timing = datetime.combine(getdate(self.event_date), dt_time(0, 0, 0))
		if self.event_end_date and self.event_end_time:
			self.event_end_datetime = datetime.combine(getdate(self.event_end_date), _to_time(self.event_end_time))
		elif self.event_end_date:
			self.event_end_datetime = datetime.combine(getdate(self.event_end_date), dt_time(0, 0, 0))

	def _auto_create_event_cost_center(self):
		"""Auto-create a per-event Cost Center when status moves to Confirmed.

		Non-blocking: Validation or duplicate errors are logged, not thrown,
		so the Event Booking save always succeeds.
		"""
		if not self.has_value_changed("booking_status"):
			return
		if self.booking_status != "Confirmed" or self.event_cost_center:
			return
		settings = self.get_settings()
		if not settings.auto_create_cost_center_per_event:
			return
		default_cc = settings.default_cost_center
		if not default_cc:
			frappe.throw(_(
				"Default Cost Center is required when Auto-Create Cost Center per Event is enabled. "
				"Please configure it in Event Booking Settings."
			))
		company = frappe.defaults.get_defaults().get("company")
		if not company:
			company = frappe.db.get_value("Cost Center", default_cc, "company")
		cc_name = f"{self.event_name} - {self.name}"
		try:
			cc = frappe.get_doc({
				"doctype": "Cost Center",
				"cost_center_name": cc_name,
				"parent_cost_center": default_cc,
				"company": company,
				"is_event_cost_center": 1,
			})
			cc.insert(ignore_permissions=True)
			self.event_cost_center = cc.name
		except frappe.DuplicateEntryError:
			# If somehow a Cost Center with this name already exists, try to link it.
			existing = frappe.db.get_value("Cost Center", {"cost_center_name": cc_name}, "name")
			if existing:
				self.event_cost_center = existing
		except frappe.ValidationError:
			frappe.log_error(title=f"Failed to auto-create Cost Center for {self.name}")

	def validate_review_requirement(self):
		settings = self.get_settings()
		if not settings.require_review:
			return
		if not frappe.db.exists("Booking Review", {
			"event_booking": self.name,
			"review_status": "Approved",
		}):
			frappe.throw(_(
				"A post-event review is required before invoicing. "
				"Please submit and approve a Booking Review for {0}."
			).format(self.name))

	# -----------------------------------------------------------------
	# Document Creation Helpers (called manually via action buttons)
	# -----------------------------------------------------------------

	def create_quotation(self):
		if self.quotation:
			return
		if not frappe.has_permission("Quotation", "create"):
			frappe.throw(
				_(
					"You do not have permission to create a Quotation. "
					"Please ask a Sales Manager to create it for you."
				),
				frappe.PermissionError,
			)
		settings = self.get_settings()
		qt = frappe.get_doc({
			"doctype": "Quotation",
			"quotation_to": "Customer",
			"party_name": self.customer,
			"event_booking": self.name,
			"cost_center": self.event_cost_center or settings.default_cost_center,
		})
		try:
			qt.insert()
		except frappe.exceptions.ValidationError as e:
			frappe.throw(_("Failed to create Quotation: {0}").format(str(e)))
		self.quotation = qt.name

	# -----------------------------------------------------------------
	# Utilities
	# -----------------------------------------------------------------

	def get_settings(self):
		return frappe.get_cached_doc("Event Booking Settings", "Event Booking Settings")


@frappe.whitelist(allow_guest=False)
def make_quotation(source_name, target_doc=None):
	if not frappe.has_permission("Event Booking", "read", source_name):
		frappe.throw(_("You do not have permission to read this Event Booking."))
	if not frappe.has_permission("Quotation", "create"):
		frappe.throw(_("You do not have permission to create a Quotation."))

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

@frappe.whitelist(allow_guest=False)
def make_project(source_name, target_doc=None):
	if not frappe.has_permission("Event Booking", "read", source_name):
		frappe.throw(_("You do not have permission to read this Event Booking."))
	if not frappe.has_permission("Project", "create"):
		frappe.throw(_("You do not have permission to create a Project."))

	def set_missing_values(source, target):
		target.project_name = source.event_name or source.name
		target.customer = source.customer
		target.expected_start_date = source.booking_date or source.event_date
		target.expected_end_date = getdate(source.event_date)

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


@frappe.whitelist(allow_guest=False)
def get_items_from_quotation(quotation_name):
	if not quotation_name:
		return []
	if not frappe.has_permission("Quotation", "read", quotation_name):
		frappe.throw(_("You do not have permission to read this Quotation."))
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


@frappe.whitelist(allow_guest=False)
def get_items_from_sales_order(sales_order_name):
	if not sales_order_name:
		return []
	if not frappe.has_permission("Sales Order", "read", sales_order_name):
		frappe.throw(_("You do not have permission to read this Sales Order."))
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


