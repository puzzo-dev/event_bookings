import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, now_datetime, today


def daily():
	"""Daily scheduled tasks."""
	for task_name, task in (
		("sync_invoice_payment_status", sync_invoice_payment_status),
		("send_unstaffed_alerts", send_unstaffed_alerts),
		("notify_managers_upcoming_events", notify_managers_upcoming_events),
	):
		try:
			task()
		except (frappe.DatabaseError, frappe.ValidationError):
			frappe.log_error(title=f"Event Bookings daily task failed: {task_name}")

	# Send pre-event reminders using global settings
	try:
		cs = frappe.get_single("Event Booking Settings")
		send_pre_event_reminders(
			days=cs.pre_event_reminder_days or 3,
			enable_whatsapp=cs.enable_whatsapp,
		)
	except (frappe.DatabaseError, frappe.ValidationError):
		frappe.log_error(title="Pre-event reminders failed")


def sync_invoice_payment_status():
	"""Transition Invoiced → Paid when linked Sales Invoice is paid."""
	events = frappe.get_all(
		"Event Booking",
		filters={"booking_status": "Invoiced", "sales_invoice": ("is", "set"), "docstatus": 1},
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
			if si_statuses.get(eb.sales_invoice) != "Paid":
				continue
			# Re-read current state before writing — the list was fetched earlier
			# and another process may have already updated or cancelled the booking.
			current = frappe.db.get_value(
				"Event Booking", eb.name, ["booking_status", "docstatus"], as_dict=True
			)
			if current and current.booking_status == "Invoiced" and current.docstatus == 1:
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
	"""Alert Event Managers with a single digest email listing all staffing shortfalls.

	Previous design sent one email per understaffed row, causing email storms on busy
	sites.  All shortfalls are now grouped by booking and delivered as one digest.
	"""
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
	if not rows:
		return

	# Group shortfalls by booking so the digest is readable
	events = {}
	for row in rows:
		if row.name not in events:
			events[row.name] = {
				"event_name": row.event_name,
				"event_timing": row.event_timing,
				"shortfalls": [],
			}
		events[row.name]["shortfalls"].append(
			_("<li>{0} – required {1}, assigned {2}</li>").format(
				row.designation, int(row.qty_required), int(row.qty_assigned)
			)
		)

	# Build a single digest message
	lines = [_("<p>The following upcoming events have staffing shortfalls:</p><ul>")]
	for ev in events.values():
		lines.append(
			"<li><strong>{0} – {1}</strong><ul>{2}</ul></li>".format(
				frappe.utils.formatdate(ev["event_timing"]),
				ev["event_name"],
				"".join(ev["shortfalls"]),
			)
		)
	lines.append("</ul>")

	try:
		_enqueue_email(
			recipients=_manager_emails,
			subject=_("Staffing Alert: {0} event(s) with shortfalls").format(len(events)),
			message="".join(lines),
			reference_doctype="Event Booking",
			reference_name=next(iter(events)),
		)
	except (frappe.DatabaseError, frappe.ValidationError):
		frappe.log_error(title=_("Staffing digest alert failed"))


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

	# Use a 24-hour rolling window — calendar-day "since midnight" causes duplicate
	# notifications when the scheduler runs near midnight.
	_dedup_since = add_to_date(now_datetime(), hours=-24)
	existing_logs = frappe.get_all(
		"Notification Log",
		filters={
			"document_type": "Event Booking",
			"document_name": ("in", [e.name for e in events]),
			"type": "Alert",
			"creation": (">=", _dedup_since),
		},
		fields=["for_user", "document_name"],
		limit_page_length=0,
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
	"""Background worker: insert Notification Log documents in batch.

	Uses ``frappe.db.bulk_insert`` (one SQL statement) instead of N individual
	``Document.insert()`` calls to avoid hammering the DB under load.
	Falls back to individual inserts if bulk_insert fails (e.g., schema mismatch).
	"""
	if not notifications:
		return

	now_ts = frappe.utils.now()
	fields = [
		"name", "type", "subject", "email_content",
		"for_user", "document_type", "document_name",
		"creation", "modified", "modified_by", "owner",
		"docstatus", "idx", "read",
	]
	values = [
		[
			frappe.generate_hash("", 10),
			n.get("type", "Alert"),
			n.get("subject", ""),
			n.get("email_content", ""),
			n.get("for_user", ""),
			n.get("document_type", ""),
			n.get("document_name", ""),
			now_ts, now_ts, "Administrator", "Administrator",
			0, 0, 0,
		]
		for n in notifications
	]

	try:
		frappe.db.bulk_insert(
			"Notification Log",
			fields=fields,
			values=values,
			ignore_duplicates=True,
		)
		frappe.db.commit()
	except Exception:
		frappe.log_error(title="Bulk notification log insert failed — retrying individually")
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
	"""Fire the ``event_booking_whatsapp_reminder`` hook for registered WhatsApp providers.

	This function is intentionally provider-agnostic.  It owns only the
	Frappe-native work (resolving the customer's mobile number from Contact)
	and then delegates delivery entirely to whatever WhatsApp app is installed
	on this site via the custom hook ``event_booking_whatsapp_reminder``.

	Any WhatsApp integration app (frappe_whatsapp, frappe_whatsapp_openwa, or a
	custom build) registers its handler in its own ``hooks.py``::

	    event_booking_whatsapp_reminder = [
	        "my_whatsapp_app.handlers.send_event_booking_reminder"
	    ]

	The handler receives ``(booking_name, phone)`` as keyword arguments::

	    def send_event_booking_reminder(booking_name, phone):
	        ...

	When no handler is registered (no WhatsApp app installed) this function is a
	complete no-op — event_bookings has zero dependency on any WhatsApp provider.

	The ``enable_whatsapp`` flag on ``Event Booking Settings`` is the per-company
	on/off gate and is checked by the caller before this function is invoked.
	"""
	try:
		if ev.party_type != "Customer" or not ev.customer:
			return

		handlers = frappe.get_hooks("event_booking_whatsapp_reminder")
		if not handlers:
			return

		# Resolve mobile from primary Contact.
		# ``is_primary_contact`` lives on tabContact, not tabDynamic Link,
		# so a JOIN is required — cannot use a simple get_value filter.
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
			(ev.customer,),
		)
		contact = result[0][0] if result else None
		if not contact:
			return
		phone = frappe.db.get_value("Contact", contact, "mobile_no")
		if not phone:
			return

		for handler in handlers:
			try:
				frappe.call(handler, booking_name=ev.name, phone=phone)
			except Exception:
				frappe.log_error(
					title=_("WhatsApp handler failed for {0}: {1}").format(ev.name, handler)
				)
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
