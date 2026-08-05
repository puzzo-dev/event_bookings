# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versioning is the app's own line and does not encode the Frappe major. Both
maintenance branches share one monotonic line: `version-15` ships this release
as `2.0.0`, `version-16` ships the same feature set plus v16 compatibility as
`2.1.0`.

## [2.1.1] - 2026-08-06

### Fixed
- Removing the settings DocType in 2.1.0 left an orphaned `Onboarding Step Map`
  row, so the onboarding showed a dead first step. Swept in the patch and on
  every migrate.
- Code-backed records (workspace, module onboarding) were never re-imported:
  `import_file_by_path` skips a file whose `modified` is older than the DB row.
  Timestamps bumped so edits actually reach the database.

### Added
- Onboarding steps "Review your Event Alerts" (opens the Notification list,
  now the only place event alerts are configured) and "Track your Booking
  Pipeline" (opens the Event Booking Pipeline report).

## [2.1.0] - 2026-08-06

Same feature set as `2.0.0` (see below), plus the Frappe v16 compatibility work
that only applies to this branch.

### Fixed
- `Create Sales Order` from a Lead booking was dead on v16: `event_booking.py`
  imported `make_customer` from `erpnext.crm.doctype.lead.lead`, which v16
  relocated to `...lead.mapper`. Conversion now goes through `erpnext_bridge`,
  which resolves either location.
- `after_migrate` was defined in `install.py` but never registered in
  `hooks.py`, so every migrate-time repair on this branch was dead code.
- `bench migrate` aborted with `Cannot edit Standard Dashboards`: the dashboard
  fixture shipped `is_standard: 1`, which `Dashboard.validate` rejects on any
  site without `developer_mode`.
- `bench migrate` aborted with `MandatoryError: [Workspace, ...]: type` once the
  app touched the workspace. v16 made `Workspace.type` mandatory; it is now
  shipped in the workspace JSON and backfilled on existing rows.
- `_fix_chart_filters_json` raised `AttributeError` on list-shaped
  `filters_json`.

### Added
- `add_to_apps_screen`, app icon/logo/favicon, and `api/permission.py`, which
  this branch was missing.

## [2.0.0] - 2026-08-06

### Removed
- **BREAKING** — the `Event Booking Settings` Single DocType, along with its
  onboarding step, workspace shortcut and `create_default_settings()`. None of
  its fields were read by any code path. Stored values are deleted by the
  `drop_event_booking_settings` patch.
- The pre-event reminder scheduler task and the `event_booking_whatsapp_reminder`
  hook. Reminders duplicated the shipped Frappe Notifications and double-sent.
- The `Workspace` fixture, which shipped `number_cards: []` and wiped the
  workspace number cards on every migrate.

### Fixed
- `Unknown column 'tabEvent Booking.event_timing'` took down the whole dashboard.
  Dashboard Charts and Number Cards referencing removed fields are now repaired
  from DocType meta on every migrate.
- `Event Booking Count Trends` plotted revenue: a duplicate record in
  `fixtures/dashboard_chart.json` shadowed the real count chart.
- Lead to Customer conversion resolves the v16 `lead.mapper` location before the
  v15 `lead.lead` one.
- The `"All Customer Groups"` fallback named a group node that
  `Customer.validate` rejects; a leaf node is resolved instead.
- ERPNext's own Quotation to Sales Order conversion no longer raises the
  blocking "Mandatory Missing" dialog.
- Workspace number cards and shortcuts are synced in `after_migrate`; the
  code-backed workspace import is hash-gated and was silently skipped.
- `api.workspace.update_chart_filters` rejects list-shaped payloads instead of
  raising `AttributeError`.

### Changed
- `Event Booking Count Trends` is grouped by Event Type, one colour-coded series
  per type, using a palette validated for both light and dark surfaces.
