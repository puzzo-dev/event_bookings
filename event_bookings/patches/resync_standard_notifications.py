"""Bring the pre-event reminders onto this release's definition, and clear the rest.

Until v2.0.1 the reminders shipped as fixtures. They now ship as standard
Notifications in ``event_bookings/notification/``, and the changeover does not
happen on its own:

  * ``import_file_by_path`` skips a file whose ``modified`` is not newer than
    the record in the database, and the fixture sync stamped those records with
    the time it ran. On any site that migrated after the shipped definition was
    written, the module folder is therefore never imported — verified on a live
    site, where a full ``bench migrate`` left the old definition untouched.

  * What it leaves behind is not cosmetic. The old condition is
    ``doc.booking_status in ('Confirmed', 'In Preparation')``. "In Preparation"
    was removed from the status model, and the state that replaced part of it —
    Paid — is not in the list, so a paid booking gets no reminder at all.

  * Folders under ``notification/`` that this release does not ship are removed.
    ``frappe.model.sync`` imports every JSON it finds there, so an exported
    orphan is not inert: it re-creates its record on every migrate. Older
    versions of the after-migrate repair wrote exactly such folders.

Forcing the import is safe here in a way it would not be on every migrate: this
runs once, and what it overwrites is a definition the app shipped, not one a
user wrote. A site that has deliberately customised a reminder should make it
non-standard, which takes it out of the sync entirely.
"""

import os
import shutil

import frappe

MODULE = "Event Bookings"

# What this release ships. Anything else under notification/ is residue.
SHIPPED = ("event_pre_event_reminder_1_day", "event_pre_event_reminder_3_days")


def execute():
	try:
		base = os.path.join(frappe.get_module_path(MODULE), "notification")
	except Exception:
		return

	_remove_unshipped_folders(base)
	_force_import_shipped(base)


def _remove_unshipped_folders(base: str):
	"""Delete exported notification folders this release does not ship."""
	if not os.path.isdir(base):
		return

	for entry in sorted(os.listdir(base)):
		folder = os.path.join(base, entry)
		if not os.path.isdir(folder) or entry in SHIPPED or entry == "__pycache__":
			continue
		# Only touch what looks like an exported notification, so an unrelated
		# directory someone put here is never removed.
		if not any(
			os.path.isfile(os.path.join(folder, f"{entry}.{ext}")) for ext in ("json", "py")
		):
			continue
		try:
			shutil.rmtree(folder)
			frappe.log_error(
				title="Event Bookings: removed orphaned notification folder",
				message=(
					f"{folder} defined a Notification this release does not ship. "
					"It was re-imported on every migrate, so the record it created "
					"could never stay deleted."
				),
			)
		except OSError:
			frappe.log_error(
				title=f"Event Bookings: could not remove {folder}",
				message=frappe.get_traceback(),
			)


def _force_import_shipped(base: str):
	"""Import each shipped definition regardless of the timestamp comparison."""
	from frappe.modules.import_file import import_file_by_path

	for slug in SHIPPED:
		path = os.path.join(base, slug, f"{slug}.json")
		if not os.path.isfile(path):
			continue
		try:
			import_file_by_path(path, force=True, ignore_version=True)
		except Exception:
			frappe.log_error(
				title=f"Event Bookings: could not import notification {slug}",
				message=frappe.get_traceback(),
			)

	frappe.db.commit()
