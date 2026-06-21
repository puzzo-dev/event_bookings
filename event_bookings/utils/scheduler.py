import frappe
from frappe import _
from frappe.utils import add_days, today


def daily():
	"""Daily scheduled tasks.

	Company-agnostic tasks run once across all data.
	Reminders are per-company because each company may have a different reminder_days setting.
	"""
	# Company-agnostic tasks
	for task_name, task in (
		("sync_invoice_payment_status", sync_invoice_payment_status),
		("send_unstaffed_alerts", send_unstaffed_alerts),
		("notify_managers_upcoming_events", notify_managers_upcoming_events),
	):
		try:
			task()
		except (frappe.DatabaseError, frappe.ValidationError):
			frappe.log_error(title=f"Event Bookings daily task failed: {task_name}")

	# Per-company reminders — reminder_days and WhatsApp flag differ per company
	for cs in frappe.get_all(
		"Event Booking Settings",
		fields=["name", "pre_event_reminder_days", "enable_whatsapp"],
	):
		try:
			send_pre_event_reminders(
				days=cs.pre_event_reminder_days or 3,
				company=cs.name,
				enable_whatsapp=cs.enable_whatsapp,
			)
		except (frappe.DatabaseError, frappe.ValidationError):
			frappe.log_error(title=f"Pre-event reminders failed for company: {cs.name}")


def sync_invoice_payment_status():
	"""Transition Invoiced → Paid when linked Sales Invoice is paid."""
	events = frappe.get_all(
		"Event Booking",
		filters={"booking_status": "Invoiced", "sales_invoice": ("is", "set")},
		fields=["name", "sales_invoice"],
		limit_page_length=0,
	)
	if not events:
		return

	sales_invoices = list({eb.sales_invoice for eb in events})
	si_statuses = frappe._dict(
		frappe.get_all("Sales Invoice", filters={"name": ("in", sales_invoices)}, fields=["name", "status"], as_list=1, limit_page_length=0)
	)

	for eb in events:
		try:
			if si_statuses.get(eb.sales_invoice) == "Paid":
				frappe.db.set_value("Event Booking", eb.name, "booking_status", "Paid")
		except (frappe.DatabaseError, frappe.ValidationError):
			frappe.log_error(title=f"Failed to sync payment status for {eb.name}")


def send_pre_event_reminders(days=3, company=None, enable_whatsapp=False):
	"""Send email reminders T-{days} days before event, scoped to one company."""
	target_date = add_days(today(), days)
	filters = {
		"event_timing": ("between", [f"{target_date} 00:00:00", f"{target_date} 23:59:59"]),
		"booking_status": ("in", ["In Preparation", "Confirmed"]),
	}
	if company:
		filters["company"] = company
	events = frappe.get_all(
		"Event Booking",
		filters=filters,
		fields=["name", "event_name", "event_timing", "customer", "party_type", "party_name", "contact_person"],
		limit_page_length=0,
	)
	if not events:
		return

	# --- batch fetch contact emails ----------------------------------------
	contact_persons = list({ev.contact_person for ev in events if ev.contact_person})
	contact_emails = {}
	if contact_persons:
		contact_emails = {
			r.name: r.email_id
			for r in frappe.get_all("Contact", filters={"name": ("in", contact_persons)}, fields=["name", "email_id"])
		}

	# --- batch fetch Customer emails (for Customer-type parties) -----------
	customers = list({ev.customer for ev in events if ev.customer})
	customer_emails = {}
	if customers:
		customer_emails = {
			r.name: r.email_id
			for r in frappe.get_all("Customer", filters={"name": ("in", customers)}, fields=["name", "email_id"])
		}

	# --- batch fetch Lead emails (for Lead-type parties) -------------------
	leads = list({ev.party_name for ev in events if ev.party_type == "Lead" and ev.party_name})
	lead_emails = {}
	if leads:
		lead_emails = {
			r.name: r.email_id
			for r in frappe.get_all("Lead", filters={"name": ("in", leads)}, fields=["name", "email_id"])
		}

	for ev in events:
		try:
			recipients = _build_event_recipients(ev, contact_emails, customer_emails, lead_emails)
			if not recipients:
				continue
			message = (
				"<p>Hello,</p>"
				"<p>This is a friendly reminder that the event <strong>{0}</strong> "
				"is scheduled for <strong>{1}</strong>.</p>"
				"<p>Please confirm all arrangements are in place.</p>"
			).format(ev.event_name, frappe.utils.formatdate(ev.event_timing))
			_enqueue_email(
				recipients=recipients,
				subject=_("Reminder: Upcoming Event – {0}").format(ev.event_name),
				message=message,
				reference_doctype="Event Booking",
				reference_name=ev.name,
			)
			if enable_whatsapp:
				_send_whatsapp_notification(ev, message)
		except (frappe.DatabaseError, frappe.ValidationError):
			frappe.log_error(title=_("Pre-event reminder failed for {0}").format(ev.name))


def _build_event_recipients(ev, contact_emails, customer_emails, lead_emails=None):
	"""Build recipient list from pre-fetched email maps, handling Lead and Customer parties."""
	recipients = []
	if ev.contact_person:
		email = contact_emails.get(ev.contact_person)
		if email:
			recipients.append(email)
	if not recipients:
		if ev.party_type == "Lead" and ev.party_name:
			email = (lead_emails or {}).get(ev.party_name)
		else:
			email = customer_emails.get(ev.customer) if ev.customer else None
		if email:
			recipients.append(email)
	return recipients




def _get_manager_emails():
	"""Return list of email addresses for enabled users with Event Manager role.

	Uses batch fetching to avoid the N+1 anti-pattern.
	"""
	managers = frappe.get_all(
		"Has Role", filters={"role": "Event Manager", "parenttype": "User"}, pluck="parent", limit_page_length=0
	)
	if not managers:
		return []
	return [
		row.email
		for row in frappe.get_all(
			"User",
			filters={"name": ("in", managers), "enabled": 1, "email": ("is", "set")},
			fields=["email"],
			distinct=True,
			limit_page_length=0,
		)
	]


def send_unstaffed_alerts():
	"""Alert Event Manager when staff requirements are not met."""
	_manager_emails = _get_manager_emails()
	if not _manager_emails:
		return

	rows = frappe.db.sql(
		"""
		SELECT
			eb.name,
			eb.event_name,
			eb.event_timing,
			esr.designation,
			esr.qty_required,
			IFNULL(esr.qty_assigned, 0) AS qty_assigned
		FROM `tabEvent Booking` eb
		INNER JOIN `tabEvent Staff Requirement` esr
			ON esr.parent = eb.name AND esr.parenttype = 'Event Booking'
		WHERE eb.booking_status = 'In Preparation'
			AND eb.event_timing >= %(today)s
			AND IFNULL(esr.qty_assigned, 0) < esr.qty_required
		ORDER BY eb.event_timing ASC
		""",
		{"today": today()},
		as_dict=True,
	)
	for row in rows:
		try:
			_enqueue_email(
				recipients=_manager_emails,
				subject=_("Staffing Alert: {0}").format(row.event_name),
				message=(
					"<p>Staffing shortfall for <strong>{0}</strong>:</p>"
					"<p><strong>{1}</strong> – required {2}, assigned {3}</p>"
				).format(
					row.event_name, row.designation,
					int(row.qty_required), int(row.qty_assigned)
				),
				reference_doctype="Event Booking",
				reference_name=row.name,
			)
		except (frappe.DatabaseError, frappe.ValidationError):
			frappe.log_error(title=_("Staffing alert failed for {0}").format(row.name))


def notify_managers_upcoming_events():
	"""Send desk notifications to Event Managers for every upcoming event within the next 7 days.

	Collects all required notifications and hands them off to a background enqueue,
	eliminating document inserts inside a nested loop.
	"""
	from_date = today()
	to_date = add_days(today(), 7)
	events = frappe.get_all(
		"Event Booking",
		filters={
			"event_timing": ("between", [f"{from_date} 00:00:00", f"{to_date} 23:59:59"]),
			"booking_status": ("in", ["New", "Quoted", "Negotiating", "Confirmed", "In Preparation", "Executed"]),
		},
		fields=["name", "event_name", "event_timing", "event_location", "booking_status"],
		limit_page_length=0,
	)
	managers = frappe.get_all("Has Role", filters={"role": "Event Manager", "parenttype": "User"}, pluck="parent", limit_page_length=0)
	if not managers or not events:
		return

	existing_logs = frappe.get_all(
		"Notification Log",
		filters={
			"document_type": "Event Booking",
			"document_name": ("in", [e.name for e in events]),
			"type": "Alert",
			"creation": (">=", f"{from_date} 00:00:00"),
		},
		fields=["for_user", "document_name"]
	)
	existing_set = {(log.for_user, log.document_name) for log in existing_logs}

	notifications = []
	for ev in events:
		for manager in managers:
			if (manager, ev.name) in existing_set:
				continue
			notifications.append({
				"subject": _("Upcoming Event: {0}").format(ev.event_name),
				"email_content": _(
					"Event {0} is scheduled for {1} at {2}. Status: {3}"
				).format(
					ev.event_name,
					frappe.utils.formatdate(ev.event_timing),
					ev.event_location or "TBD",
					ev.booking_status,
				),
				"for_user": manager,
				"document_type": "Event Booking",
				"document_name": ev.name,
			})

	if notifications:
		frappe.enqueue(
			"event_bookings.utils.scheduler._insert_notification_logs",
			queue="short",
			notifications=notifications,
		)


def _insert_notification_logs(notifications):
	"""Background worker: insert Notification Log documents in batch."""
	for n in notifications:
		try:
			frappe.get_doc({
				"doctype": "Notification Log",
				"type": "Alert",
				**n,
			}).insert(ignore_permissions=True)
		except (frappe.DatabaseError, frappe.ValidationError):
			frappe.log_error(title=_("Manager notification failed"))


def _send_whatsapp_notification(ev, message):
	"""Send WhatsApp notification if integration is available.

	Uses ev.customer (already fetched by caller) — no extra DB round-trip.
	Skips gracefully for Lead-type parties (no Customer link to look up).
	"""
	try:
		if ev.party_type != "Customer" or not ev.customer:
			return
		contact = frappe.db.get_value(
			"Dynamic Link",
			{"parenttype": "Contact", "link_doctype": "Customer", "link_name": ev.customer},
			"parent",
			order_by="is_primary_contact desc, creation desc",
		)
		if not contact:
			return
		phone = frappe.db.get_value("Contact", contact, "mobile_no")
		if not phone:
			return
		# Placeholder for actual WhatsApp API call
		frappe.logger("event_bookings").info(f"WhatsApp notification queued for {ev.name} to {phone}")
	except (frappe.DatabaseError, frappe.ValidationError):
		frappe.log_error(title=_("WhatsApp notification failed for {0}").format(ev.name))


def _enqueue_email(recipients, subject, message, reference_doctype, reference_name):
	"""Queue an email in the background using the public frappe.sendmail API."""
	frappe.sendmail(
		recipients=recipients,
		subject=subject,
		message=message,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		now=False,
	)
