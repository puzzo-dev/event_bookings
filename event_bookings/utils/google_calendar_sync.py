"""Google Calendar sync for Event Booking.

Piggybacks on Frappe's existing Google Calendar OAuth infrastructure
(frappe.integrations.doctype.google_calendar) so no additional credentials
are needed — users just configure a Google Calendar doc the same way they
would for the native Frappe Event.

Push flow  (Event Booking → Google):
  after_insert / on_update  →  push_to_google_calendar()
  on_trash                  →  delete_from_google_calendar()

Pull flow  (Google → Frappe):
  Not implemented here.  Events created directly in Google Calendar will not
  automatically create Event Bookings (that would require a full booking
  workflow, customer selection, etc.).  Users can trigger a manual sync from
  the Google Calendar doc form if they want to pull.
"""

import datetime

import frappe
from frappe import _
from googleapiclient.errors import HttpError

from frappe.integrations.doctype.google_calendar.google_calendar import (
	format_date_according_to_google_calendar,
	get_google_calendar_object,
)
from frappe.utils import get_datetime, getdate, get_time


def _should_sync(doc):
	"""Return True when this document should be pushed to Google Calendar."""
	return (
		bool(doc.sync_with_google_calendar)
		and not doc.pulled_from_google_calendar
		and bool(doc.google_calendar)
		and frappe.db.exists("Google Calendar", {"name": doc.google_calendar})
	)


def _build_event_body(doc):
	"""Map Event Booking fields to a Google Calendar events.insert/patch body."""
	# Combine date + time fields into Python datetime objects
	event_date = getdate(doc.event_date)
	start_time = get_time(doc.event_time or "00:00:00")
	end_time = get_time(doc.event_end_time or doc.event_time or "23:59:00")

	start_dt = get_datetime(datetime.datetime.combine(event_date, start_time))
	end_dt = get_datetime(datetime.datetime.combine(event_date, end_time))

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
	body.update(
		format_date_according_to_google_calendar(
			False,   # not all-day — Event Bookings always have a time
			start_dt,
			end_dt,
		)
	)
	return body


# ── Push: Event Booking → Google Calendar ──────────────────────────


def push_to_google_calendar(doc, method=None):
	"""Insert or update this Event Booking in Google Calendar.

	Registered as after_insert and on_update on the Event Booking DocType.
	"""
	if not _should_sync(doc):
		return

	if not doc.google_calendar_event_id:
		_insert_event(doc)
	else:
		_update_event(doc)


def _insert_event(doc):
	try:
		google_calendar, account = get_google_calendar_object(doc.google_calendar)
	except Exception:
		frappe.log_error(
			title=f"Google Calendar — could not get object for {doc.name}",
			message=frappe.get_traceback(),
		)
		return

	if not account.push_to_google_calendar:
		return

	try:
		event = (
			google_calendar.events()
			.insert(
				calendarId=doc.google_calendar_id,
				body=_build_event_body(doc),
				sendUpdates="all",
			)
			.execute()
		)
		frappe.db.set_value(
			"Event Booking",
			doc.name,
			"google_calendar_event_id",
			event.get("id"),
			update_modified=False,
		)
		frappe.msgprint(_("Event Booking synced with Google Calendar."))
	except HttpError as err:
		frappe.log_error(
			title=f"Google Calendar — insert failed for {doc.name}",
			message=str(err),
		)
		frappe.throw(
			_("Google Calendar — could not create event, error code {0}.").format(err.resp.status)
		)


def _update_event(doc):
	# Skip during initial save (creation == modified means we are in after_insert path)
	if doc.modified == doc.creation:
		return

	try:
		google_calendar, account = get_google_calendar_object(doc.google_calendar)
	except Exception:
		frappe.log_error(
			title=f"Google Calendar — could not get object for {doc.name}",
			message=frappe.get_traceback(),
		)
		return

	if not account.push_to_google_calendar:
		return

	try:
		google_calendar.events().patch(
			calendarId=doc.google_calendar_id,
			eventId=doc.google_calendar_event_id,
			body=_build_event_body(doc),
			sendUpdates="all",
		).execute()
	except HttpError as err:
		frappe.log_error(
			title=f"Google Calendar — update failed for {doc.name}",
			message=str(err),
		)


# ── Delete: cancel event in Google Calendar on trash ───────────────


def delete_from_google_calendar(doc, method=None):
	"""Set the Google Calendar event status to 'cancelled' when the booking is deleted."""
	if not doc.google_calendar_event_id or not doc.google_calendar:
		return

	try:
		google_calendar, _account = get_google_calendar_object(doc.google_calendar)
		google_calendar.events().patch(
			calendarId=doc.google_calendar_id,
			eventId=doc.google_calendar_event_id,
			body={"status": "cancelled"},
		).execute()
	except HttpError as err:
		frappe.log_error(
			title=f"Google Calendar — delete failed for {doc.name}",
			message=str(err),
		)
	except Exception:
		frappe.log_error(
			title=f"Google Calendar — unexpected error deleting {doc.name}",
			message=frappe.get_traceback(),
		)
