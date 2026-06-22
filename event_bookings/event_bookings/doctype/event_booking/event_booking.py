import frappe
from datetime import datetime, time as dt_time, timedelta
from frappe import _
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe.utils import today, getdate, flt, get_datetime, now_datetime


# Valid booking status transitions.
# Maps each status to the set of allowed next statuses.
# System Manager bypasses this check to allow manual corrections.
VALID_TRANSITIONS = {
	"New": {"Quoted", "Negotiating", "Confirmed", "Cancelled"},
	"Quoted": {"Negotiating", "Confirmed", "Cancelled", "New"},
	"Negotiating": {"Quoted", "Confirmed", "Cancelled"},
	"Confirmed": {"In Preparation", "Cancelled"},
	"In Preparation": {"Executed", "Cancelled"},
	"Executed": {"Invoiced", "Cancelled"},
	"Invoiced": {"Paid", "Executed"},
	"Paid": {"Invoiced"},      # allow reversal by manager only
	"Cancelled": {"New"},      # allow re-opening by manager only
}

# Statuses that represent committed/financial activity.
# These require a Customer party type AND cannot be deleted without cancelling first.
_COMMITTED_STATUSES = frozenset({
	"Confirmed", "In Preparation", "Executed", "Invoiced", "Paid"
})
_PROTECTED_STATUSES = _COMMITTED_STATUSES       # delete guard alias
_CUSTOMER_REQUIRED_STATUSES = _COMMITTED_STATUSES  # party-type guard alias


class EventBooking(Document):
	def validate(self):
		self._sync_datetime_fields()
		self.validate_dates()
		_prev = self.get_doc_before_save()
		self._validate_status_transition(_prev)
		self._validate_party_for_status()
		self._sync_customer_field()
		if self._linked_docs_changed(_prev):
			self.calculate_totals()
		if self.booking_status == "Invoiced":
			self.validate_review_requirement()

	def before_submit(self):
		"""Submission locks the booking. Only allow when at a committed status."""
		if self.booking_status not in _COMMITTED_STATUSES:
			frappe.throw(
				_(
					"Event Booking can only be submitted when its status is one of: {0}. "
					"Current status is '{1}'."
				).format(", ".join(sorted(_COMMITTED_STATUSES)), self.booking_status)
			)

	def on_cancel(self):
		"""Align booking_status with docstatus=2 and warn about linked submitted documents."""
		frappe.db.set_value(
			"Event Booking", self.name, "booking_status", "Cancelled", update_modified=False
		)
		self.booking_status = "Cancelled"

		linked_submitted = []
		for fieldname, doctype in [
			("quotation", "Quotation"),
			("sales_order", "Sales Order"),
			("sales_invoice", "Sales Invoice"),
			("material_request", "Material Request"),
			("stock_entry", "Stock Entry"),
		]:
			linked_name = getattr(self, fieldname, None)
			if linked_name:
				docstatus = frappe.db.get_value(doctype, linked_name, "docstatus")
				if docstatus == 1:
					linked_submitted.append(f"{doctype}: {linked_name}")

		if linked_submitted:
			frappe.msgprint(
				_(
					"Warning: The following submitted documents remain linked to this booking "
					"and will <strong>not</strong> be automatically cancelled:<br><ul>{0}</ul>"
					"Cancel them manually to maintain a clean audit trail."
				).format("".join(f"<li>{doc}</li>" for doc in linked_submitted)),
				title=_("Linked Documents Still Active"),
				indicator="orange",
				alert=True,
			)

	def before_delete(self):
		"""Extra guard for Draft bookings in committed statuses.
		Submitted docs (docstatus=1) cannot be deleted by Frappe regardless.
		"""
		if self.booking_status in _COMMITTED_STATUSES:
			frappe.throw(
				_(
					"Cannot delete Event Booking {0} — it is in '{1}' status. "
					"Submit or cancel the booking first."
				).format(self.name, self.booking_status),
				frappe.PermissionError,
			)

	def _validate_status_transition(self, _prev=None):
		"""Enforce allowed status transitions unless user is System Manager."""
		if self.is_new() or not self.has_value_changed("booking_status"):
			return

		if "System Manager" in frappe.get_roles():
			return

		old_status = (_prev or self.get_doc_before_save()).booking_status
		new_status = self.booking_status

		allowed = VALID_TRANSITIONS.get(old_status, set())
		if new_status not in allowed:
			frappe.throw(
				_(
					"Invalid status transition from '{0}' to '{1}'. "
					"Allowed next statuses are: {2}"
				).format(old_status, new_status, ", ".join(allowed))
			)

	def _validate_party_for_status(self):
		"""Enforce that Confirmed and beyond statuses require a Customer, not a Lead."""
		if self.booking_status in _CUSTOMER_REQUIRED_STATUSES and self.party_type != "Customer":
			frappe.throw(
				_(
					"Party Type must be 'Customer' before moving to '{0}' status. "
					"Use Actions → Convert Lead to Customer first."
				).format(self.booking_status)
			)

	def _sync_customer_field(self):
		"""Keep the hidden customer field in sync when party_type is Customer.
		This ensures backward compatibility with linked documents (Project, etc.)."""
		if self.party_type == "Customer":
			self.customer = self.party_name
		else:
			self.customer = None

	def _linked_docs_changed(self, _prev=None):
		"""Return True if any linked document field has changed from previous save."""
		previous = _prev or self.get_doc_before_save()
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
		def _to_time(t):
			if isinstance(t, str):
				hour, minute, second = map(int, t.split(":"))
				return dt_time(hour, minute, second)
			if isinstance(t, timedelta):
				seconds = int(t.total_seconds())
				hour = seconds // 3600
				minute = (seconds % 3600) // 60
				second = seconds % 60
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
	# Utilities
	# -----------------------------------------------------------------

	def get_settings(self):
		"""Return the Event Booking Settings for this booking's company.

		Falls back to a safe defaults dict when no settings record exists yet,
		so saves always succeed even on freshly installed or partially configured sites.
		"""
		company = self.company or frappe.db.get_default("Company")
		if company and frappe.db.exists("Event Booking Settings", company):
			return frappe.get_cached_doc("Event Booking Settings", company)
		return frappe._dict({
			"require_review": 0,
			"pre_event_reminder_days": 3,
			"enable_whatsapp": 0,
			"default_income_account": None,
			"default_cogs_account": None,
			"default_damages_account": None,
			"default_warehouse": None,
			"events_warehouse": None,
			"damages_warehouse": None,
		})


@frappe.whitelist(allow_guest=False)
def make_quotation(source_name, target_doc=None):
	if not frappe.has_permission("Event Booking", "read", source_name):
		frappe.throw(_("You do not have permission to read this Event Booking."))
	if not frappe.has_permission("Quotation", "create"):
		frappe.throw(_("You do not have permission to create a Quotation."))

	def set_missing_values(source, target):
		target.quotation_to = source.party_type
		target.party_name = source.party_name
		target.event_booking = source.name

	doclist = get_mapped_doc(
		"Event Booking",
		source_name,
		{
			"Event Booking": {
				"doctype": "Quotation",
				"field_map": {
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
		# Project requires a Customer; only link if party is already a Customer
		if source.party_type == "Customer":
			target.customer = source.party_name
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
def convert_lead_and_update_booking(booking_name):
	"""Convert the Lead linked to an Event Booking into a Customer, then update the booking.

	Delegates ERPNext-specific Lead→Customer logic to erpnext_bridge so this
	function never imports from erpnext directly and remains callable even on
	Frappe-only sites (where it will raise a user-friendly error instead).

	Returns {"customer": <new_customer_name>, "already_existed": bool}.
	"""
	from event_bookings.utils.erpnext_bridge import make_customer_from_lead

	if not frappe.has_permission("Event Booking", "write", booking_name):
		frappe.throw(_("You do not have permission to modify this Event Booking."))

	# Guard: Customer DocType must exist (requires ERPNext)
	if not frappe.db.exists("DocType", "Customer"):
		frappe.throw(_("Customer management is not available. ERPNext must be installed."))

	if not frappe.has_permission("Customer", "create"):
		frappe.throw(_("You do not have permission to create a Customer."))

	booking = frappe.get_doc("Event Booking", booking_name)

	if booking.party_type != "Lead":
		frappe.throw(_("This booking is not linked to a Lead."))

	lead_name = booking.party_name

	# Reuse an existing Customer already created from this Lead — no duplicate
	existing_customer = frappe.db.get_value("Customer", {"lead_name": lead_name}, "name")
	if existing_customer:
		customer_name = existing_customer
		already_existed = True
	else:
		customer_doc = make_customer_from_lead(lead_name)
		customer_doc.insert()
		customer_name = customer_doc.name
		already_existed = False

	# Update the booking to point to the new Customer
	booking.party_type = "Customer"
	booking.party_name = customer_name
	booking.customer = customer_name
	booking.save()

	return {"customer": customer_name, "already_existed": already_existed}


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
