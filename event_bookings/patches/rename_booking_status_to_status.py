"""Rename Event Booking.booking_status to status.

The field held the booking's lifecycle state and was called `booking_status`,
which meant none of Frappe's handling for a status field applied to it. That
handling is keyed on the literal fieldname:

  get_fields_in_list_view  fetches a field named `status` for the list whether
                           or not it is a column
  setup_columns            drops it from the columns when the doctype has an
                           indicator, so it is never shown twice
  get_indicator            colours the pill from it, via the doctype's states

ERPNext's Sales Order and Sales Invoice both rely on exactly this, which is why
neither needs anything beyond a read-only field. This app was reimplementing
those three behaviours by hand instead.

Ordering matters and is why this patch is last. The doctype sync has already
created the empty `status` column by the time post_model_sync patches run, and
`booking_status` is still there with the data in it. Every earlier patch in
patches.txt was written against `booking_status` and still refers to it: on a
site where they have not run yet they execute first, against the old column, and
this patch then carries their result across. That is also why none of them were
rewritten — a patch records a migration at a point in time, and editing one to
use a name that did not exist when it ran would make it operate on the wrong
column.
"""

import frappe

_DOCTYPE = "Event Booking"
_OLD = "booking_status"
_NEW = "status"


def execute():
	if not frappe.db.table_exists(_DOCTYPE):
		return

	has_old = frappe.db.has_column(_DOCTYPE, _OLD)
	has_new = frappe.db.has_column(_DOCTYPE, _NEW)

	if has_old and has_new:
		from frappe.model.utils.rename_field import rename_field

		# Copies the values across and follows the field through Property
		# Setters, saved report columns and per-user list settings.
		rename_field(_DOCTYPE, _OLD, _NEW)
		frappe.db.commit()

		_drop_old_column()

	_rewrite_stored_references()
	frappe.db.commit()


def _drop_old_column():
	"""Remove the old column, but only once every row has been carried over.

	An orphan column holding a second copy of the lifecycle state is the kind of
	thing that gets read by accident later, so it goes — but not on trust. If a
	single row disagrees, the column stays and the mismatch is reported, because
	losing a booking's status is worse than leaving a column behind.
	"""
	mismatched = frappe.db.sql(
		f"""SELECT COUNT(*) FROM `tab{_DOCTYPE}`
		    WHERE NOT (`{_NEW}` <=> `{_OLD}`)"""
	)[0][0]

	if mismatched:
		frappe.log_error(
			title="Event Bookings: booking_status not dropped",
			message=(
				f"{mismatched} row(s) still differ between {_OLD} and {_NEW}. "
				"The old column has been left in place; reconcile before removing it."
			),
		)
		return

	frappe.db.sql(f"ALTER TABLE `tab{_DOCTYPE}` DROP COLUMN `{_OLD}`")


def _rewrite_stored_references():
	"""Follow the rename into the records that name the field in stored text.

	Charts, cards and notifications keep the fieldname inside a JSON blob or a
	condition string, so nothing about a column rename reaches them. Their
	module-folder definitions are updated in the same commit as this patch, but
	the sync only re-imports a file whose timestamp beats the record's, so the
	database is corrected here directly.
	"""
	targets = (
		("Dashboard Chart", "filters_json"),
		("Number Card", "filters_json"),
		("Notification", "condition"),
		("Notification", "message"),
		("Notification", "subject"),
	)

	for doctype, fieldname in targets:
		if not frappe.db.table_exists(doctype):
			continue
		try:
			rows = frappe.get_all(
				doctype,
				filters={fieldname: ["like", f"%{_OLD}%"]},
				fields=["name", fieldname],
			)
		except Exception:
			continue

		for row in rows:
			value = row.get(fieldname)
			if not value or _OLD not in str(value):
				continue
			frappe.db.set_value(
				doctype,
				row.name,
				fieldname,
				str(value).replace(_OLD, _NEW),
				update_modified=False,
			)
