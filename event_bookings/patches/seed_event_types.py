from event_bookings.utils.seed import seed_event_types


def execute():
	"""Seed default event types if they don't exist."""
	seed_event_types()
