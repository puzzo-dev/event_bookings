"""Structured logging and optional Sentry integration helper for Event Bookings.

Add `sentry_dsn` to site_config.json and install `sentry-sdk` to enable Sentry.
"""

from __future__ import annotations

import json
import traceback
import frappe


def _get_sentry_client():
	"""
	Return the sentry_sdk module if Sentry is configured, or None.

	Deliberately avoids a module-level cache: Gunicorn prefork workers share
	module state across requests, so a cached client from a previous request
	may hold a stale DSN (e.g. after a site config change) or a connection
	that was forked before the worker was fully initialised.

	sentry_sdk.init() is safe to call repeatedly — it reinitialises only when
	the DSN actually changes.  The call is cheap (no network I/O) so calling
	it on every event is negligible compared to the HTTP cost of the Sentry
	envelope itself.
	"""
	dsn = frappe.get_conf().get("sentry_dsn")
	if not dsn:
		return None

	try:
		import sentry_sdk
	except ImportError:
		frappe.logger().warning(
			"sentry_dsn is set but sentry-sdk is not installed. "
			"Run `pip install sentry-sdk` to enable Sentry."
		)
		return None

	# Re-init only when needed.  get_client() returns a NullClient when
	# Sentry is uninitialised; a NullClient has no .dsn attribute set.
	if not getattr(sentry_sdk.get_client(), "dsn", None):
		sentry_sdk.init(
			dsn=dsn,
			environment=frappe.get_conf().get("sentry_environment", "production"),
		)
	return sentry_sdk


def capture_event(event: str, context: dict | None = None, level: str = "info"):
	ctx = context or {}
	payload = {"event": event, "level": level, "context": ctx, "site": frappe.local.site}
	frappe.logger().info(json.dumps(payload, default=str))

	client = _get_sentry_client()
	if client:
		with client.new_scope() as scope:
			for key, value in ctx.items():
				scope.set_extra(key, value)
			scope.set_tag("event", event)
			client.capture_message(event, level=level)


def capture_exception(
	event: str,
	exception: Exception | None = None,
	context: dict | None = None,
	message: str | None = None,
):
	ctx = context or {}
	exc = exception or frappe.get_traceback()
	payload = {
		"event": event,
		"level": "error",
		"context": ctx,
		"traceback": exc if isinstance(exc, str) else traceback.format_exc(),
		"site": frappe.local.site,
	}
	frappe.log_error(
		title=event,
		message=json.dumps(payload, default=str) if not message else f"{message}\n\n{json.dumps(payload, default=str)}",
	)

	client = _get_sentry_client()
	if client:
		with client.new_scope() as scope:
			for key, value in ctx.items():
				scope.set_extra(key, value)
			scope.set_tag("event", event)
			client.capture_exception(error=exc if not isinstance(exc, str) else None)
