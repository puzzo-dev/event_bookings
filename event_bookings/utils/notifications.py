import frappe
from frappe.utils import formatdate


def format_whatsapp_message(template, doc):
	"""Format a WhatsApp message from a template string and document."""
	return template.format(
		event_name=doc.event_name,
		customer=doc.customer,
		event_date=formatdate(doc.event_date),
		event_location=doc.event_location,
	)


def send_event_reminder(event_doc, days_until):
	"""Send email/WhatsApp reminder to staff and event planner."""
	settings = frappe.get_cached_doc("Event Settings", "Event Settings")

	subject = f"Reminder: {event_doc.event_name} in {days_until} day(s)"
	message = (
		f"Event <b>{event_doc.event_name}</b> for {event_doc.customer} "
		f"is scheduled on {formatdate(event_doc.event_date)} "
		f"at {event_doc.event_location}.<br><br>"
		f"Please ensure all preparations are on track."
	)

	recipients = _get_event_recipients(event_doc, settings)
	if not recipients:
		return

	try:
		frappe.sendmail(
			recipients=recipients,
			subject=subject,
			message=message,
			reference_doctype="Event Booking",
			reference_name=event_doc.name,
		)
	except Exception:
		frappe.log_error(
			f"Failed to send event reminder for {event_doc.name}",
			"Event Bookings Email",
		)

	if settings.enable_whatsapp:
		_send_whatsapp_reminder(event_doc, days_until)


def send_unstaffed_alert(event_doc, unstaffed_roles):
	"""Notify Event Manager about unfilled staff positions."""
	settings = frappe.get_cached_doc("Event Settings", "Event Settings")

	roles_list = ", ".join(f"{r['designation']} (need {r['gap']} more)" for r in unstaffed_roles)
	subject = f"Staffing Alert: {event_doc.event_name}"
	message = (
		f"Event <b>{event_doc.event_name}</b> on {formatdate(event_doc.event_date)} "
		f"has unfilled staff positions:<br><br>{roles_list}<br><br>"
		f"Please assign staff as soon as possible."
	)

	recipients = []
	if settings.notification_email:
		recipients.append(settings.notification_email)
	if event_doc.event_planner:
		planner_email = frappe.db.get_value("Sales Partner", event_doc.event_planner, "email")
		if planner_email:
			recipients.append(planner_email)

	if recipients:
		try:
			frappe.sendmail(
				recipients=recipients,
				subject=subject,
				message=message,
				reference_doctype="Event Booking",
				reference_name=event_doc.name,
			)
		except Exception:
			frappe.log_error(
				f"Failed to send unstaffed alert for {event_doc.name}",
				"Event Bookings Email",
			)


def _get_event_recipients(event_doc, settings):
	"""Collect email recipients for event notifications."""
	recipients = []
	if settings.notification_email:
		recipients.append(settings.notification_email)
	if event_doc.contact_person:
		contact_email = frappe.db.get_value("Contact", event_doc.contact_person, "email_id")
		if contact_email:
			recipients.append(contact_email)
	if event_doc.event_planner:
		planner_email = frappe.db.get_value("Sales Partner", event_doc.event_planner, "email")
		if planner_email:
			recipients.append(planner_email)
	return recipients


def _send_whatsapp_reminder(event_doc, days_until):
	"""Send WhatsApp notification via Frappe's messaging integration."""
	template = (
		"Reminder: {event_name} for {customer} is in "
		+ str(days_until)
		+ " day(s) on {event_date} at {event_location}."
	)
	try:
		message = format_whatsapp_message(template, event_doc)
		frappe.publish_realtime(
			"whatsapp_notification",
			{"message": message, "event_booking": event_doc.name},
		)
	except Exception:
		frappe.log_error(
			f"WhatsApp notification failed for {event_doc.name}",
			"Event Bookings WhatsApp",
		)
