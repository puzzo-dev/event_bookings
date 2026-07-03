import unittest
from types import SimpleNamespace
from unittest.mock import patch

from event_bookings.utils.notifications import format_whatsapp_message


class TestFormatWhatsAppMessage(unittest.TestCase):
	"""Unit tests for the WhatsApp message formatter."""

	def _make_doc(self, **kwargs):
		defaults = {
			"event_name": "Annual Gala",
			"party_name": "Acme Corp",
			"event_date": "2026-07-15",
			"event_time": "18:00:00",
			"event_location": "Grand Ballroom",
		}
		defaults.update(kwargs)
		return SimpleNamespace(**defaults)

	@patch("frappe.utils.formatdate", side_effect=lambda d: d)
	def test_basic_substitution(self, _fmt):
		tpl = "Event: {event_name} for {party_name} on {event_date} at {event_location}"
		result = format_whatsapp_message(tpl, self._make_doc())
		self.assertEqual(
			result,
			"Event: Annual Gala for Acme Corp on 2026-07-15 at Grand Ballroom",
		)

	@patch("frappe.utils.formatdate", side_effect=lambda d: d)
	def test_partial_template(self, _fmt):
		tpl = "Reminder: {event_name} is coming up!"
		result = format_whatsapp_message(tpl, self._make_doc())
		self.assertEqual(result, "Reminder: Annual Gala is coming up!")

	@patch("frappe.utils.formatdate", return_value="15 Jul 2026")
	def test_formatdate_called(self, mock_fmt):
		tpl = "Date: {event_date}"
		doc = self._make_doc()
		result = format_whatsapp_message(tpl, doc)
		mock_fmt.assert_called_once_with("2026-07-15")
		self.assertEqual(result, "Date: 15 Jul 2026")

	@patch("frappe.utils.formatdate", side_effect=lambda d: d)
	def test_empty_fields(self, _fmt):
		tpl = "{event_name} | {party_name} | {event_location}"
		doc = self._make_doc(event_name="", party_name="", event_location="")
		result = format_whatsapp_message(tpl, doc)
		self.assertEqual(result, " |  | ")

	@patch("frappe.utils.formatdate", side_effect=lambda d: d)
	def test_special_characters_in_fields(self, _fmt):
		tpl = "Event: {event_name}"
		doc = self._make_doc(event_name="John & Jane's Wedding — 2026")
		result = format_whatsapp_message(tpl, doc)
		self.assertEqual(result, "Event: John & Jane's Wedding — 2026")

	@patch("frappe.throw")
	@patch("frappe.log_error")
	@patch("frappe.utils.formatdate", side_effect=lambda d: d)
	def test_missing_placeholder_raises(self, _fmt, mock_log, mock_throw):
		tpl = "Event: {event_name} by {organizer}"
		format_whatsapp_message(tpl, self._make_doc())
		mock_throw.assert_called_once()
