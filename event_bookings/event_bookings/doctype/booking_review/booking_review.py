# Copyright (c) 2026, Avril Beetails and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import sanitize_html, validate_email_address


class BookingReview(Document):
	def validate(self):
		"""Enforce data constraints at the controller level regardless of entry path."""
		if self.rating is not None and self.rating != "":
			try:
				rating_int = int(self.rating)
				if rating_int not in range(1, 6):
					frappe.throw(_("Rating must be between 1 and 5."))
			except (ValueError, TypeError):
				frappe.throw(_("Rating must be a whole number between 1 and 5."))

		if self.review_text and len(self.review_text) > _MAX_REVIEW_TEXT:
			frappe.throw(
				_("Review text must not exceed {0} characters.").format(_MAX_REVIEW_TEXT)
			)

		allowed_statuses = {"Submitted", "Approved", "Rejected"}
		if self.review_status and self.review_status not in allowed_statuses:
			frappe.throw(_("Invalid Review Status '{0}'.").format(self.review_status))


_MAX_REVIEW_TEXT = 5000
_ALLOWED_STATUSES = {"Executed", "Invoiced", "Paid"}


_RATE_LIMIT_WINDOW = 3600  # 1 hour
_MAX_REVIEWS_PER_WINDOW = 3


@frappe.whitelist(allow_guest=False)
def submit_review(event_booking, rating=None, review_text=None):
	"""Submit a review for an event. Reviewer is derived from the linked Customer.

	Rate-limited: max 3 reviews per customer per hour.
	Requires authentication (called from external frontend with customer context).
	"""
	if not event_booking:
		frappe.throw(_("Event Booking is required."))

	if not frappe.db.exists("Event Booking", event_booking):
		frappe.throw(_("Event Booking not found."))

	# --- state guard: only review completed events --------------------------------
	booking_status = frappe.db.get_value("Event Booking", event_booking, "booking_status")
	if booking_status not in _ALLOWED_STATUSES:
		frappe.throw(
			_(
				"Reviews are only allowed for events that have been completed. "
				"Current status: '{0}'."
			).format(booking_status)
		)

	# --- derive reviewer from Customer --------------------------------------------
	customer = frappe.db.get_value("Event Booking", event_booking, "customer")
	if not customer:
		frappe.throw(_("No customer linked to this Event Booking."))

	# --- authorization: verify caller is linked to this customer ----------------
	if not _caller_linked_to_customer(customer):
		frappe.throw(
			_(
				"You are not authorized to submit a review for this event. "
				"Only contacts linked to the customer can submit reviews."
			),
			frappe.PermissionError,
		)

	reviewer_name, reviewer_email = _get_customer_contact_info(customer)
	if not reviewer_email:
		frappe.throw(_("No email found for customer {0}. Please add a contact.").format(customer))

	# --- rate limiting per customer+event -----------------------------------------
	_cache_key = f"event_booking_review_limit:{customer}:{event_booking}"
	_count = frappe.cache().get(_cache_key) or 0
	if int(_count) >= _MAX_REVIEWS_PER_WINDOW:
		frappe.throw(_("Rate limit exceeded. Please try again later."))
	frappe.cache().set(_cache_key, int(_count) + 1, expires_in_sec=_RATE_LIMIT_WINDOW)

	# --- email validation ---------------------------------------------------------
	try:
		validate_email_address(reviewer_email, throw=True)
	except frappe.exceptions.ValidationError:
		frappe.throw(_("Invalid reviewer email address."))

	# --- rating validation --------------------------------------------------------
	try:
		rating_int = int(rating) if rating is not None else 3
	except (ValueError, TypeError):
		frappe.throw(_("Rating must be an integer between 1 and 5."))
	if not (1 <= rating_int <= 5):
		frappe.throw(_("Rating must be between 1 and 5."))

	# --- review text sanitization & length validation ---------------------------
	review_text = sanitize_html(review_text or "").strip()
	if len(review_text) > _MAX_REVIEW_TEXT:
		frappe.throw(_("Review text must not exceed {0} characters.").format(_MAX_REVIEW_TEXT))

	# --- duplicate prevention (same customer + event, 24h window) ----------------
	last_review = frappe.db.get_value(
		"Booking Review",
		{"event_booking": event_booking, "reviewer_email": reviewer_email},
		"creation",
		order_by="creation desc",
	)
	if last_review and frappe.utils.time_diff_in_hours(frappe.utils.now(), last_review) < 24:
		frappe.throw(_("You have already submitted a review for this event within the last 24 hours."))

	review = frappe.get_doc({
		"doctype": "Booking Review",
		"event_booking": event_booking,
		"reviewer_name": (reviewer_name or customer).strip()[:140],
		"reviewer_email": reviewer_email,
		"rating": rating_int,
		"review_text": review_text,
		"is_published": 0,
		"review_status": "Submitted",
		"submitted_via": "Direct",  # customer submitted via authenticated session
	})
	review.insert()
	return {"message": "Review submitted successfully.", "name": review.name}


def _get_primary_contact_for_customer(customer):
	"""Return the name of the primary Contact for a Customer, joining Contact for is_primary_contact ordering.

	`is_primary_contact` lives on `tabContact`, not `tabDynamic Link`, so a JOIN is required.
	"""
	result = frappe.db.sql(
		"""
		SELECT dl.parent
		FROM `tabDynamic Link` dl
		INNER JOIN `tabContact` c ON c.name = dl.parent
		WHERE dl.parenttype = 'Contact'
		  AND dl.link_doctype = 'Customer'
		  AND dl.link_name = %s
		ORDER BY c.is_primary_contact DESC, dl.creation DESC
		LIMIT 1
		""",
		(customer,),
	)
	return result[0][0] if result else None


def _get_customer_contact_info(customer):
	"""Return (name, email) for the customer's primary contact, falling back to customer defaults."""
	name = None
	email = None

	# Try primary contact (single query via JOIN to respect is_primary_contact ordering)
	contact = _get_primary_contact_for_customer(customer)
	if contact:
		contact_info = frappe.db.get_value("Contact", contact, ["first_name", "email_id"], as_dict=True) or {}
		name = contact_info.get("first_name")
		email = contact_info.get("email_id")

	# Fallback: customer email_id
	if not email:
		email = frappe.db.get_value("Customer", customer, "email_id")
	if not name:
		name = frappe.db.get_value("Customer", customer, "customer_name")

	return name, email


def _caller_linked_to_customer(customer):
	"""Return True if the current user is linked to the given customer."""
	# Allow system administrator (standard Frappe root user)
	if frappe.session.user == frappe.conf.get("admin_user", "Administrator"):
		return True

	# Check if user is linked via Contact > Dynamic Link
	contact = _get_primary_contact_for_customer(customer)
	if contact:
		contact_user = frappe.db.get_value("Contact", contact, "user")
		if contact_user == frappe.session.user:
			return True

	# Check if user is linked via Customer.user (if exists)
	customer_user = frappe.db.get_value("Customer", customer, "user")
	if customer_user == frappe.session.user:
		return True

	# Check if user has a role that can manage reviews
	if frappe.has_permission("Booking Review", "write"):
		return True

	return False
