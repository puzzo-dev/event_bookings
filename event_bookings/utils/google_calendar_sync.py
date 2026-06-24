import frappe
from frappe import _


def push_to_google_calendar(doc, method=None):
	"""Push an Event Booking to Google Calendar on insert/update."""
	if not doc.sync_with_google_calendar or not doc.google_calendar:
		return

	try:
		account = frappe.get_doc("Google Calendar", doc.google_calendar)
		if not account.enable:
			return

		google_calendar, calendar_id = get_google_calendar_object(account)

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
	"""Remove the event from Google Calendar when the booking is deleted."""
	if not doc.google_calendar_event_id or not doc.google_calendar:
		return

	try:
		account = frappe.get_doc("Google Calendar", doc.google_calendar)
		google_calendar, calendar_id = get_google_calendar_object(account)
		google_calendar.events().delete(
			calendarId=calendar_id,
			eventId=doc.google_calendar_event_id,
		).execute()
	except Exception:
		frappe.log_error(
			title=_("Google Calendar delete failed for {0}").format(doc.name),
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
		body["start"] = {
			"dateTime": format_date_according_to_google_calendar(
				False, f"{start_date} {doc.event_time}"
			),
		}
		end_time = doc.event_end_time or doc.event_time
		body["end"] = {
			"dateTime": format_date_according_to_google_calendar(
				False, f"{end_date} {end_time}"
			),
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


def get_google_calendar_object(account):
	"""Wrapper — delegates to Frappe's built-in Google Calendar helpers."""
	from frappe.integrations.doctype.google_calendar.google_calendar import (
		get_google_calendar_object as _get,
	)
	return _get(account)


def format_date_according_to_google_calendar(all_day, date_time_str):
	from frappe.integrations.doctype.google_calendar.google_calendar import (
		format_date_according_to_google_calendar as _fmt,
	)
	return _fmt(all_day, date_time_str)
