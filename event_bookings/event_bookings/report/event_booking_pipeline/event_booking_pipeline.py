# Re-export from the canonical report module
from event_bookings.report.event_booking_pipeline.event_booking_pipeline import (
	execute,
)

__all__ = ["execute"]
