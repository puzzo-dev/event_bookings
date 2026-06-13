import frappe
from event_bookings.utils.notifications import send_event_reminder, send_unstaffed_alert
from frappe.utils import add_days, today


def daily():
	"""Daily scheduled tasks."""
	for task in (
		sync_invoice_payment_status,
		lambda: send_pre_event_reminders(days=3),
		lambda: send_pre_event_reminders(days=1),
		send_unstaffed_alerts,
	):
		try:
			task()
		except Exception:
			frappe.log_error(title=f"Event Bookings daily task failed: {getattr(task, '__name__', 'lambda')}")


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
				doc = frappe.get_doc("Event Booking", eb.name)
				doc.booking_status = "Paid"
				doc.save(ignore_permissions=True)
		except Exception:
			frappe.log_error(title=f"Failed to sync payment status for {eb.name}")


def send_pre_event_reminders(days=3):
	"""Send reminders to staff T-N days before event."""
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
		doc = frappe.get_doc("Event Booking", ev.name)
		send_event_reminder(doc, days)


def send_unstaffed_alerts():
	"""Alert Event Manager when staff requirements are not met."""
	events = frappe.get_all(
		"Event Booking",
		filters={"booking_status": "In Preparation"},
		fields=["name"],
	)
	for ev in events:
		doc = frappe.get_doc("Event Booking", ev.name)
		unstaffed = []
		for req in doc.staff_requirements:
			gap = (req.qty_required or 0) - (req.qty_assigned or 0)
			if gap > 0:
				unstaffed.append({"designation": req.designation, "gap": gap})
		if unstaffed:
			send_unstaffed_alert(doc, unstaffed)
