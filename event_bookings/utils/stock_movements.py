"""Project submitted Stock Entries onto an Event Booking's Items Used table.

The table is a derived view, not an input, and it answers one question: what
was actually used to deliver this event. Anything that takes stock out for an
event is a Stock Entry — that is the document that changes the ledger — so the
booking reads those rather than asking anyone to retype them. Tagging Event
Booking on a Stock Entry is the whole interface; it does not matter whether the
entry was made from the booking's own button or by hand in the warehouse.

Both ways of taking stock out count as use — an issue for what is consumed, a
transfer for what comes back — and the entry type decides which entries qualify.
Which kind it was is not repeated here: the Stock Entry already records that,
and this table exists to list the items, not to restate the movement.

A return leg — stock coming back in afterwards — is deliberately not a row.
It is not a use, it is the reversal of one, and listing it would double-count
the same chairs as both taken and returned. What came back belongs in the stock
ledger, which is where it already is.

Accounting is the ledger's business too; this table only answers "what did this
event use".
"""

import frappe

# Stock Entry Type -> how the stock was used. Types not listed here did not take
# stock out for an event: Material Receipt is the return leg, and Manufacture,
# Repack and Send to Subcontractor are unrelated. All are skipped.
_MOVEMENT_BY_ENTRY_TYPE = {
	"Material Issue": "Issued",
	"Material Consumption for Manufacture": "Issued",
	"Material Transfer": "Transferred",
	"Material Transfer for Manufacture": "Transferred",
}

_CHILD_DOCTYPE = "Service Item"
_PARENT_DOCTYPE = "Event Booking"
_PARENTFIELD = "event_items"


def movement_for_entry_type(entry_type: str | None) -> str | None:
	"""How a Stock Entry Type used stock, or None if it did not use any.

	Kept as the inclusion rule rather than as a column: the answer decides
	whether an entry's lines are listed at all, but it is not written onto the
	row because the Stock Entry is where the movement type lives.
	"""
	return _MOVEMENT_BY_ENTRY_TYPE.get((entry_type or "").strip())


def collect_movements(booking: str) -> list[dict]:
	"""Everything submitted Stock Entries used for this booking, oldest first.

	The tag is read from the Stock Entry, which is where the user sets it, and
	from the individual line where it has been set there instead — ERPNext's
	accounting dimension puts the field on both, and warehouse staff use either.
	"""
	if not booking:
		return []

	rows = frappe.db.sql(
		"""
		SELECT se.name AS stock_entry, se.stock_entry_type, se.posting_date,
		       sed.item_code, sed.item_name, sed.qty, sed.uom, sed.stock_uom,
		       sed.description, sed.s_warehouse, sed.t_warehouse
		FROM `tabStock Entry Detail` sed
		INNER JOIN `tabStock Entry` se ON se.name = sed.parent
		WHERE se.docstatus = 1
		  AND (se.event_booking = %(booking)s OR sed.event_booking = %(booking)s)
		ORDER BY se.posting_date ASC, se.name ASC, sed.idx ASC
		""",
		{"booking": booking},
		as_dict=True,
	)

	movements = []
	for r in rows:
		movement = movement_for_entry_type(r.stock_entry_type)
		if not movement:
			continue
		movements.append({
			"item_code": r.item_code,
			"item_name": r.item_name,
			"qty": r.qty,
			"uom": r.uom,
			"stock_uom": r.stock_uom,
			"description": r.description,
			# Where the stock came from — an issue has only a source, a
			# transfer has both and the source is what it was drawn against.
			"warehouse": r.s_warehouse or r.t_warehouse,
			"stock_entry": r.stock_entry,
			"posting_date": r.posting_date,
		})
	return movements


def sync_booking(booking: str) -> int:
	"""Rebuild a booking's Items Used table. Returns the row count.

	Written straight to the child table rather than through the parent
	document. The rows are a projection of stock that has already moved, so
	there is nothing for the parent's validation to decide, and a booking is
	frequently submitted or cancelled by the time an entry is made against it —
	going through save() would refuse exactly when the table most needs to stay
	accurate.
	"""
	if not booking or not frappe.db.exists(_PARENT_DOCTYPE, booking):
		return 0

	movements = collect_movements(booking)

	frappe.db.delete(_CHILD_DOCTYPE, {"parent": booking, "parenttype": _PARENT_DOCTYPE})

	for idx, row in enumerate(movements, start=1):
		child = frappe.new_doc(_CHILD_DOCTYPE)
		child.update(row)
		child.parent = booking
		child.parenttype = _PARENT_DOCTYPE
		child.parentfield = _PARENTFIELD
		child.idx = idx
		child.db_insert()

	return len(movements)
