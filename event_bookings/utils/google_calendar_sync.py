"""Google Calendar sync for Event Booking.

Piggybacks on Frappe's existing Google Calendar OAuth infrastructure
(frappe.integrations.doctype.google_calendar) so no additional credentials
are needed — users just configure a Google Calendar doc the same way they
would for the native Frappe Event.

Push flow  (Event Booking → Google):
  on_update / on_update_after_submit / on_cancel  →  push_to_google_calendar()
  on_trash                                        →  delete_from_google_calendar()

All HTTP calls to the Google Calendar API are executed in a background job
(enqueued with ``enqueue_after_commit=True``) so that:
  - the booking's DB transaction is not held open across network latency,
  - a Google API outage or timeout does not fail the user's save,
  - row locks on ``tabEvent Booking`` are released immediately.

Pull flow  (Google → Frappe):
  Not implemented here.  Events created directly in Google Calendar will not
  automatically create Event Bookings (that would require a full booking
  workflow, customer selection, etc.).  Users can trigger a manual sync from
  the Google Calendar doc form if they want to pull.
"""

import datetime

import frappe
from frappe import _
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

	body = {
		"summary": f"{doc.event_name} ({doc.customer})" if doc.customer else doc.event_name,
		"description": (
			f"Booking Ref: {doc.name}\n"
			f"Customer: {doc.customer or ''}\n"
			f"Status: {doc.booking_status}\n"
			f"Location: {doc.event_location or ''}\n"
		) + (f"Special Requirements: {doc.special_requirements}\n" if doc.special_requirements else ""),
		"location": doc.event_location or "",
	}

	# A cancelled booking has to read as cancelled in the calendar too. on_cancel
	# is wired to this same push, and the body never said anything about status,
	# so cancelling a booking sent Google an ordinary update: the event stayed on
	# everyone's calendar, at the original time, looking live. Setting it here
	# rather than deleting the event keeps the history — Google renders a
	# cancelled event as cancelled — and it also covers the status-only cancel a
	# draft booking uses, which never reaches on_cancel at all.
	if doc.docstatus == 2 or doc.booking_status == "Cancelled":
		body["status"] = "cancelled"

	try:
		from frappe.integrations.doctype.google_calendar.google_calendar import (
			format_date_according_to_google_calendar,
		)
		body.update(format_date_according_to_google_calendar(False, start_dt, end_dt))
	except ImportError:
		# frappe.utils.get_time_zone does not exist on v15 or v16 — the name is
		# get_system_timezone, so this fallback raised AttributeError instead of
		# falling back, on exactly the sites without the Google Calendar module.
		tz = frappe.utils.get_system_timezone()
		body["start"] = {"dateTime": start_dt.isoformat(), "timeZone": tz}
		body["end"] = {"dateTime": end_dt.isoformat(), "timeZone": tz}
	return body


# ── Push: Event Booking → Google Calendar ──────────────────────────


def push_to_google_calendar(doc, method=None):
	"""Enqueue a Google Calendar insert/update for this Event Booking.

	Registered as on_update, on_update_after_submit, and on_cancel on the
	Event Booking DocType. The actual HTTP call runs in a background job so
	the booking's DB transaction is not held open across Google's network
	latency and a Google outage does not fail the user's save.
	"""
	if not _should_sync(doc):
		return

	# Nothing the calendar shows has changed on most saves - recalculating
	# totals after an invoice, stamping a lifecycle date, a status the body
	# does not mention - and each of those queued a job that fetched
	# credentials and called Google to push an identical event.
	if not _calendar_fields_changed(doc):
		return

	frappe.enqueue(
		"event_bookings.utils.google_calendar_sync._sync_in_background",
		booking_name=doc.name,
		queue="default",
		enqueue_after_commit=True,
		job_id=f"google_calendar_sync:{doc.name}",
		# job_id alone only names the job; without this, ten saves in a row
		# queued ten identical pushes.
		deduplicate=True,
	)


# What _build_event_body actually reads. A change to anything else is invisible
# in the calendar, so it is not worth a round trip to Google.
_CALENDAR_FIELDS = (
	"event_name", "customer", "event_date", "event_time", "event_end_time",
	"event_location", "special_requirements", "booking_status",
	"google_calendar", "sync_with_google_calendar",
)


def _calendar_fields_changed(doc) -> bool:
	"""True when a field the calendar entry shows has changed on this save.

	A new booking, a cancel, or a document with no before-image all count as
	changed: there is nothing to compare against and the calendar has to be
	told.
	"""
	if doc.docstatus == 2 or doc.is_new():
		return True

	before = doc.get_doc_before_save()
	if before is None:
		return True

	return any(doc.get(f) != before.get(f) for f in _CALENDAR_FIELDS)


def _sync_in_background(booking_name):
	"""Background job: insert or update the Google Calendar event.

	Re-reads the booking from the DB so it always sees the committed state,
	not the in-memory snapshot from the doc_event hook.
	"""
	doc = frappe.get_doc("Event Booking", booking_name)
	if not _should_sync(doc):
		return

	if not doc.google_calendar_event_id:
		_insert_event(doc)
	else:
		_update_event(doc)


def _calendar_id(account, doc=None) -> str:
	"""Which Google calendar to write to.

	Taken from the linked Google Calendar record rather than the booking's own
	google_calendar_id. That field is marked read_only, which is a form
	constraint and not a server one — the API will happily set it — so trusting
	it let a caller aim this app's writes at any calendar the site's credentials
	can reach. The Google Calendar doctype is the thing an administrator
	actually grants, so it is what decides the destination.
	"""
	calendar_id = getattr(account, "google_calendar_id", None)
	if calendar_id:
		return calendar_id
	# Older rows may predate the field on the account; fall back to the booking
	# rather than fail the sync outright.
	return getattr(doc, "google_calendar_id", None) or ""


def _insert_event(doc):
	try:
		from googleapiclient.errors import HttpError
		from frappe.integrations.doctype.google_calendar.google_calendar import (
			format_date_according_to_google_calendar,
			get_google_calendar_object,
		)
	except ImportError:
		frappe.log_error(title="Google Calendar — missing dependency", message=frappe.get_traceback())
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
		event = (
			google_calendar.events()
			.insert(
				calendarId=_calendar_id(account, doc),
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
	except HttpError as err:
		frappe.log_error(
			title=f"Google Calendar — insert failed for {doc.name}",
			message=str(err),
		)
		# In a background job, frappe.throw would crash the worker and trigger
		# RQ retries (which would re-call Google). Log and return instead.
		frappe.msgprint(
			_("Google Calendar — could not create event, error code {0}.").format(err.resp.status)
		)


def _update_event(doc):
	# Skip during initial save (creation == modified means we are in after_insert path)
	if doc.modified == doc.creation:
		return

	try:
		from googleapiclient.errors import HttpError
		from frappe.integrations.doctype.google_calendar.google_calendar import get_google_calendar_object
	except ImportError:
		frappe.log_error(title="Google Calendar — missing dependency", message=frappe.get_traceback())
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
			calendarId=_calendar_id(account, doc),
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
	"""Enqueue cancellation of the Google Calendar event when the booking is trashed.

	The HTTP call runs in a background job so the trash transaction is not
	held open across Google's network latency.
	"""
	if not doc.google_calendar_event_id or not doc.google_calendar:
		return

	frappe.enqueue(
		"event_bookings.utils.google_calendar_sync._delete_in_background",
		booking_name=doc.name,
		google_calendar=doc.google_calendar,
		google_calendar_id=doc.google_calendar_id,
		google_calendar_event_id=doc.google_calendar_event_id,
		queue="default",
		enqueue_after_commit=True,
		job_id=f"google_calendar_delete:{doc.name}",
	)


def _delete_in_background(booking_name, google_calendar, google_calendar_id, google_calendar_event_id):
	"""Background job: cancel the Google Calendar event."""
	try:
		from googleapiclient.errors import HttpError
		from frappe.integrations.doctype.google_calendar.google_calendar import get_google_calendar_object
	except ImportError:
		frappe.log_error(title="Google Calendar — missing dependency", message=frappe.get_traceback())
		return

	try:
		google_calendar_obj, account = get_google_calendar_object(google_calendar)
		google_calendar_obj.events().patch(
			calendarId=_calendar_id(account) or google_calendar_id,
			eventId=google_calendar_event_id,
			body={"status": "cancelled"},
		).execute()
	except HttpError as err:
		frappe.log_error(
			title=f"Google Calendar — delete failed for {booking_name}",
			message=str(err),
		)
	except Exception:
		frappe.log_error(
			title=f"Google Calendar — unexpected error deleting {booking_name}",
			message=frappe.get_traceback(),
		)
