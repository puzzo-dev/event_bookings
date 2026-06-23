import frappe
from frappe.utils import add_days, today


def daily():
	"""Daily scheduled tasks."""
	for name, task in (
		("sync_invoice_payment_status", sync_invoice_payment_status),
		("send_pre_event_reminders_3d", lambda: send_pre_event_reminders(days=3)),
		("send_pre_event_reminders_1d", lambda: send_pre_event_reminders(days=1)),
		("send_unstaffed_alerts", send_unstaffed_alerts),
	):
		try:
			task()
		except Exception:
			frappe.log_error(
				title=f"Event Bookings daily task failed: {name}",
				message=frappe.get_traceback(),
			)


def hourly():
	"""Hourly scheduled tasks."""
	pass


def sync_invoice_payment_status():
	"""Transition Invoiced → Paid when linked Sales Invoice is paid."""
	events = frappe.get_all(
		"Event Booking",
		filters={"booking_status": "Invoiced", "sales_invoice": ("is", "set")},
		fields=["name", "sales_invoice"],
	)
	for eb in events:
		try:
			si_status = frappe.db.get_value("Sales Invoice", eb.sales_invoice, "status")
			if si_status == "Paid":
				frappe.db.set_value("Event Booking", eb.name, "booking_status", "Paid")
		except Exception:
			frappe.log_error(title=f"Failed to sync payment status for {eb.name}")


def send_pre_event_reminders(days=3):
	"""Send reminders to staff T-3 and T-1 days before event."""
	target_date = add_days(today(), days)
	events = frappe.get_all(
		"Event Booking",
		filters={
			"event_date": target_date,
			"booking_status": ("in", ["In Preparation", "Confirmed"]),
		},
		fields=["name", "event_name", "event_date"],
	)
	for ev in events:
		try:
			_notify_event_managers(
				ev,
				subject=f"Reminder: Event '{ev.event_name}' is on {ev.event_date}",
				message=(
					f"<p>This is a {days}-day reminder for the event <b>{ev.event_name}</b> "
					f"({ev.name}) scheduled on <b>{ev.event_date}</b>.</p>"
					"<p>Please ensure all preparations are on track.</p>"
				),
			)
		except Exception:
			frappe.log_error(
				title=f"Pre-event reminder failed for {ev.name}",
				message=frappe.get_traceback(),
			)


def send_unstaffed_alerts():
	"""Alert Event Manager when staff requirements are not met."""
	events = frappe.get_all(
		"Event Booking",
		filters={"booking_status": "In Preparation"},
		fields=["name"],
	)
	for ev in events:
		try:
			doc = frappe.get_doc("Event Booking", ev.name)
			understaffed = []
			for req in doc.staff_requirements:
				if (req.qty_assigned or 0) < req.qty_required:
					understaffed.append(
						f"{req.designation}: {req.qty_assigned}/{req.qty_required} assigned"
					)
			if not understaffed:
				continue

			message = (
				f"<p>Event <b>{doc.event_name}</b> ({doc.name}) is under-staffed:</p>"
				+ "<ul>"
				+ "".join(f"<li>{line}</li>" for line in understaffed)
				+ "</ul>"
			)
			_notify_event_managers(
				doc,
				subject=f"Under-staffed Alert: {doc.event_name}",
				message=message,
			)
		except Exception:
			frappe.log_error(
				title=f"Unstaffed alert failed for {ev.name}",
				message=frappe.get_traceback(),
			)


def _notify_event_managers(doc, subject, message):
	"""Send an email to all users with the Event Manager role."""
	managers = get_event_managers()
	if not managers:
		return

	for user in managers:
		try:
			frappe.sendmail(
				recipients=[user.email],
				subject=subject,
				message=message,
				reference_doctype=doc.doctype,
				reference_name=doc.name,
			)
		except Exception:
			frappe.log_error(
				title=f"Failed to send event notification to {user.email}",
				message=frappe.get_traceback(),
			)


def get_event_managers():
	"""Return all active users with the Event Manager role."""
	return frappe.get_all(
		"User",
		filters={
			"enabled": 1,
			"name": ("in", frappe.get_all("Has Role", filters={"role": "Event Manager"}, pluck="parent")),
		},
		fields=["email"],
	)
