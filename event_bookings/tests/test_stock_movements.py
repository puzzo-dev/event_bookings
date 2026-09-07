"""Items Used as a projection of what a booking consumed.

An Event Booking carries two item lists answering different questions. Ordered
Items is what the customer bought, from the Quotation or Sales Order. Items
Used is what was actually used to deliver it, from Stock Entries tagged to the
booking — issue what is consumed, transfer what comes back, both are uses.

A return leg is not a use and must not appear, or the same chairs would be
counted as both taken and returned.
"""

import unittest
from unittest.mock import MagicMock, patch

_MODULE = "event_bookings.utils.stock_movements"


class TestWhichEntriesCount(unittest.TestCase):
	"""The classification is an inclusion rule, not a column on the row."""

	def _movement(self, entry_type):
		from event_bookings.utils.stock_movements import movement_for_entry_type

		return movement_for_entry_type(entry_type)

	def test_issue_counts(self):
		"""Consumed at the event and not coming back — still a use."""
		self.assertEqual(self._movement("Material Issue"), "Issued")
		self.assertEqual(self._movement("Material Consumption for Manufacture"), "Issued")

	def test_transfer_counts(self):
		self.assertEqual(self._movement("Material Transfer"), "Transferred")
		self.assertEqual(self._movement("Material Transfer for Manufacture"), "Transferred")

	def test_return_leg_is_not_a_use(self):
		"""Stock coming back is the reversal of a use, not another one."""
		self.assertIsNone(self._movement("Material Receipt"))

	def test_unrelated_entry_types_are_not_uses(self):
		for t in ("Manufacture", "Repack", "Send to Subcontractor", "Disassemble"):
			self.assertIsNone(self._movement(t), f"{t} does not use stock for an event")

	def test_blank_entry_type(self):
		self.assertIsNone(self._movement(None))
		self.assertIsNone(self._movement(""))


class TestCollectMovements(unittest.TestCase):
	def _collect(self, rows):
		frappe_mock = MagicMock()
		frappe_mock.db.sql.return_value = rows
		with patch(f"{_MODULE}.frappe", frappe_mock):
			from event_bookings.utils.stock_movements import collect_movements

			return collect_movements("EVT-0001"), frappe_mock

	# collect_movements reads as_dict rows by attribute, which MagicMock provides.
	def _row(self, **kw):
		base = {
			"stock_entry": "MAT-STE-0001", "stock_entry_type": "Material Issue",
			"posting_date": "2026-09-08", "item_code": "ITEM-1", "item_name": "Item One",
			"qty": 5.0, "uom": "Nos", "stock_uom": "Nos", "description": "",
			"s_warehouse": "Stores - TC", "t_warehouse": None,
		}
		base.update(kw)
		return MagicMock(**base, **{"get": lambda k, d=None: base.get(k, d)})

	def test_only_submitted_entries_are_queried(self):
		"""A draft has not moved anything, so it is not a movement yet."""
		_, m = self._collect([])
		sql = m.db.sql.call_args[0][0]
		self.assertIn("docstatus = 1", sql)

	def test_tag_read_from_header_or_line(self):
		"""ERPNext puts the dimension on both, and staff use either."""
		_, m = self._collect([])
		sql = m.db.sql.call_args[0][0]
		self.assertIn("se.event_booking", sql)
		self.assertIn("sed.event_booking", sql)

	def test_non_movement_entry_types_are_dropped(self):
		rows, _ = self._collect([self._row(stock_entry_type="Manufacture")])
		self.assertEqual(rows, [])

	def test_row_carries_no_movement_column(self):
		"""The Stock Entry owns the movement type; the row only lists the item."""
		rows, _ = self._collect([self._row(stock_entry_type="Material Issue")])
		self.assertNotIn("movement", rows[0])
		self.assertEqual(rows[0]["item_code"], "ITEM-1")
		self.assertEqual(rows[0]["stock_entry"], "MAT-STE-0001")

	def test_issue_uses_source_warehouse(self):
		rows, _ = self._collect([self._row(stock_entry_type="Material Issue",
		                                   s_warehouse="Stores - TC", t_warehouse=None)])
		self.assertEqual(rows[0]["warehouse"], "Stores - TC")

	def test_receipt_produces_no_row(self):
		"""The return leg is filtered out with the other non-uses."""
		rows, _ = self._collect([self._row(stock_entry_type="Material Receipt",
		                                   s_warehouse=None, t_warehouse="Stores - TC")])
		self.assertEqual(rows, [])

	def test_transfer_is_credited_to_its_source(self):
		"""A transfer has both warehouses; it was drawn against the source."""
		rows, _ = self._collect([self._row(stock_entry_type="Material Transfer",
		                                   s_warehouse="Stores - TC", t_warehouse="Venue - TC")])
		self.assertEqual(rows[0]["warehouse"], "Stores - TC")


if __name__ == "__main__":
	unittest.main()
