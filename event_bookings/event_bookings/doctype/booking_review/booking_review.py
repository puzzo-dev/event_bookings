# Copyright (c) 2026, I-Varse Technologies NG and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import sanitize_html, validate_email_address


_MAX_REVIEW_TEXT = 5000
_ALLOWED_STATUSES = {"Executed", "Invoiced", "Paid"}
_RATE_LIMIT_WINDOW = 3600  # 1 hour
_MAX_REVIEWS_PER_WINDOW = 3


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


@frappe.whitelist(allow_guest=False)
def submit_review(event_booking, rating=None, review_text=None):
	"""Submit a review for a completed event booking.

	Allowed callers:
	- Administrator / system API user (public form submits with owner credentials in bg)
	- Event Manager (desk submission on behalf of the customer)
	- A Frappe user linked to the booking's Customer via Contact.user or Customer.user

	Reviewer identity is always derived from the Event Booking's linked Customer so
	that reviews are correctly attributed regardless of who submits them.

	Rate-limited: max {_MAX_REVIEWS_PER_WINDOW} submissions per customer+event per hour.
	"""
	if not event_booking:
		frappe.throw(_("Event Booking is required."))

	if not frappe.db.exists("Event Booking", event_booking):
		frappe.throw(_("Event Booking not found."))

	# Only review completed events
	booking_status = frappe.db.get_value("Event Booking", event_booking, "booking_status")
	if booking_status not in _ALLOWED_STATUSES:
		frappe.throw(
			_(
				"Reviews are only allowed for events that have been completed. "
				"Current status: '{0}'."
			).format(booking_status)
		)

	# Derive reviewer from Customer — Event Booking uses party_type / party_name
	party_type, party_name = frappe.db.get_value(
		"Event Booking", event_booking, ["party_type", "party_name"]
	)
	if party_type != "Customer":
		frappe.throw(
			_(
				"Reviews can only be submitted for bookings with a Customer party type. "
				"Current party type: '{0}'."
			).format(party_type)
		)
	customer = party_name
	if not customer:
		frappe.throw(_("No customer linked to this Event Booking."))

	# Authorization: determine caller type and submitted_via in one pass
	submitted_via = _get_submitted_via(customer)
	if submitted_via is None:
		frappe.throw(
			_(
				"You are not authorized to submit a review for this event. "
				"Only the customer, an Event Manager, or the system API can submit reviews."
			),
			frappe.PermissionError,
		)

	reviewer_name, reviewer_email = _get_customer_contact_info(customer)
	if not reviewer_email:
		frappe.throw(_("No email found for customer {0}. Please add a contact.").format(customer))

	# Rate limiting per customer+event
	_cache_key = f"event_booking_review_limit:{customer}:{event_booking}"
	_count = frappe.cache().get(_cache_key) or 0
	if int(_count) >= _MAX_REVIEWS_PER_WINDOW:
		frappe.throw(_("Rate limit exceeded. Please try again later."))
	frappe.cache().set(_cache_key, int(_count) + 1, expires_in_sec=_RATE_LIMIT_WINDOW)

	# Email validation
	try:
		validate_email_address(reviewer_email, throw=True)
	except frappe.exceptions.ValidationError:
		frappe.throw(_("Invalid reviewer email address."))

	# Rating validation
	try:
		rating_int = int(rating) if rating is not None else 3
	except (ValueError, TypeError):
		frappe.throw(_("Rating must be an integer between 1 and 5."))
	if not (1 <= rating_int <= 5):
		frappe.throw(_("Rating must be between 1 and 5."))

	# Review text sanitization and length validation
	review_text = sanitize_html(review_text or "").strip()
	if len(review_text) > _MAX_REVIEW_TEXT:
		frappe.throw(_("Review text must not exceed {0} characters.").format(_MAX_REVIEW_TEXT))

	# Duplicate prevention (same customer + event, 24h window)
	last_review = frappe.db.get_value(
		"Booking Review",
		{"event_booking": event_booking, "reviewer_email": reviewer_email},
		"creation",
		order_by="creation desc",
	)
	if last_review and frappe.utils.time_diff_in_hours(frappe.utils.now(), last_review) < 24:
		frappe.throw(_("A review for this event was already submitted within the last 24 hours."))

	review = frappe.get_doc({
		"doctype": "Booking Review",
		"event_booking": event_booking,
		"reviewer_name": (reviewer_name or customer).strip()[:140],
		"reviewer_email": reviewer_email,
		"rating": rating_int,
		"review_text": review_text,
		"is_published": 0,
		"review_status": "Submitted",
		"submitted_via": submitted_via,
	})
	review.insert(ignore_permissions=True)
	return {"message": "Review submitted successfully.", "name": review.name}


def _get_submitted_via(customer):
	"""Return the submitted_via label for the current caller, or None if not authorised.

	Priority:
	1. Administrator / system API user → "Public Link"
	   (public form authenticates with owner API credentials in the background)
	2. Event Manager role → "Event Manager"
	   (desk submission; manager knows the customer from the booking context)
	3. Frappe user linked to the customer → "Direct"
	   (customer self-service via portal or direct API call)
	"""
	user = frappe.session.user

	if user == frappe.conf.get("admin_user", "Administrator") or user == "Administrator":
		return "Public Link"

	roles = frappe.get_roles(user)
	if "Event Manager" in roles:
		return "Event Manager"

	if _user_linked_to_customer(user, customer):
		return "Direct"

	return None


def _user_linked_to_customer(user, customer):
	"""Return True if user is linked to the given Customer via Contact or Customer record."""
	contact = _get_primary_contact_for_customer(customer)
	if contact:
		contact_user = frappe.db.get_value("Contact", contact, "user")
		if contact_user == user:
			return True

	customer_user = frappe.db.get_value("Customer", customer, "user")
	if customer_user == user:
		return True

	return False


def _get_primary_contact_for_customer(customer):
	"""Return the name of the primary Contact for a Customer."""
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

	contact = _get_primary_contact_for_customer(customer)
	if contact:
		contact_info = frappe.db.get_value("Contact", contact, ["first_name", "email_id"], as_dict=True) or {}
		name = contact_info.get("first_name")
		email = contact_info.get("email_id")

	if not email:
		email = frappe.db.get_value("Customer", customer, "email_id")
	if not name:
		name = frappe.db.get_value("Customer", customer, "customer_name")

	return name, email
