import frappe
from frappe import _

# Fields that affect the Google Calendar event body — skip sync when only
# unrelated fields (cost_center, quotation, sales_order, etc.) change.
_CALENDAR_FIELDS = frozenset({
	"event_name", "event_date", "event_time", "event_end_time",
	"booking_status", "event_location", "party_name",
})


def push_to_google_calendar(doc, method=None):
	"""Enqueue Google Calendar sync so HTTP never blocks the save request."""
	if not doc.sync_with_google_calendar or not doc.google_calendar:
		return
	before = doc.get_doc_before_save()
	if before and not any(
		getattr(doc, f) != getattr(before, f, None) for f in _CALENDAR_FIELDS
	):
		return
	frappe.enqueue(
		"event_bookings.utils.google_calendar_sync._sync_to_google_calendar",
		booking_name=doc.name,
		queue="default",
		now=frappe.flags.in_test,
	)


def _sync_to_google_calendar(booking_name):
	"""Background worker: push a single Event Booking to Google Calendar."""
	doc = frappe.get_doc("Event Booking", booking_name)
	if not doc.sync_with_google_calendar or not doc.google_calendar:
		return

	try:
		account = frappe.get_doc("Google Calendar", doc.google_calendar)
		if not account.enable:
			return

		google_calendar, calendar_id = _get_google_calendar_object(account)
		if google_calendar is None:
			return

		if doc.google_calendar_event_id:
			_update_event(google_calendar, calendar_id, doc)
		else:
			_insert_event(google_calendar, calendar_id, doc)

	except Exception:
		frappe.log_error(
			title=_("Google Calendar sync failed for {0}").format(doc.name),
			message=frappe.get_traceback(),
		)


def delete_from_google_calendar(doc, method=None):
	"""Enqueue Google Calendar event deletion so on_trash never blocks on HTTP."""
	if not doc.google_calendar_event_id or not doc.google_calendar:
		return
	frappe.enqueue(
		"event_bookings.utils.google_calendar_sync._delete_from_google_calendar_background",
		booking_name=doc.name,
		google_calendar=doc.google_calendar,
		google_calendar_event_id=doc.google_calendar_event_id,
		queue="default",
		now=frappe.flags.in_test,
	)


def _delete_from_google_calendar_background(
	booking_name, google_calendar, google_calendar_event_id
):
	"""Background worker: delete a single Google Calendar event."""
	try:
		account = frappe.get_doc("Google Calendar", google_calendar)
		gc, calendar_id = _get_google_calendar_object(account)
		if gc is None:
			return
		gc.events().delete(
			calendarId=calendar_id,
			eventId=google_calendar_event_id,
		).execute()
	except Exception:
		frappe.log_error(
			title=_("Google Calendar delete failed for {0}").format(booking_name),
			message=frappe.get_traceback(),
		)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_event_body(doc):
	party_label = f"{doc.party_type}: " if doc.party_type else ""
	body = {
		"summary": f"{doc.event_name} ({doc.party_name})",
		"description": (
			f"Booking Ref: {doc.name}\n"
			f"{party_label}{doc.party_name}\n"
			f"Status: {doc.booking_status}\n"
			f"Location: {doc.event_location or ''}\n"
		) + (f"Special Requirements: {doc.special_requirements}\n" if doc.special_requirements else ""),
		"location": doc.event_location or "",
	}

	start_date = doc.event_date
	end_date = doc.event_date

	if doc.event_time:
		fmt = _format_date_according_to_google_calendar
		body["start"] = {
			"dateTime": fmt(False, f"{start_date} {doc.event_time}"),
		}
		end_time = doc.event_end_time or doc.event_time
		body["end"] = {
			"dateTime": fmt(False, f"{end_date} {end_time}"),
		}
	else:
		body["start"] = {"date": str(start_date)}
		body["end"] = {"date": str(end_date)}

	return body


def _insert_event(google_calendar, calendar_id, doc):
	body = _build_event_body(doc)
	result = google_calendar.events().insert(calendarId=calendar_id, body=body).execute()
	frappe.db.set_value(
		"Event Booking",
		doc.name,
		{
			"google_calendar_event_id": result.get("id"),
			"google_calendar_id": calendar_id,
		},
	)


def _update_event(google_calendar, calendar_id, doc):
	body = _build_event_body(doc)
	google_calendar.events().update(
		calendarId=calendar_id,
		eventId=doc.google_calendar_event_id,
		body=body,
	).execute()


def _get_google_calendar_object(account):
	"""Delegate to Frappe's built-in Google Calendar helper; return None if unavailable."""
	try:
		from frappe.integrations.doctype.google_calendar.google_calendar import (
			get_google_calendar_object as _get,
		)
		return _get(account)
	except ImportError:
		frappe.log_error(
			title="Google Calendar integration unavailable",
			message="frappe.integrations.doctype.google_calendar not found.",
		)
		return None, None


def _format_date_according_to_google_calendar(all_day, date_time_str):
	try:
		from frappe.integrations.doctype.google_calendar.google_calendar import (
			format_date_according_to_google_calendar as _fmt,
		)
		return _fmt(all_day, date_time_str)
	except ImportError:
		return date_time_str
