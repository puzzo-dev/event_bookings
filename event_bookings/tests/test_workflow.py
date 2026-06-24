import frappe
from frappe.tests.utils import FrappeTestCase

from event_bookings.tests.fixtures import get_or_create_test_party, get_or_create_test_event_type


class TestEventBookingWorkflow(FrappeTestCase):
	def setUp(self):
		self.test_party_type, self.test_party_name = get_or_create_test_party()
		self.test_event_type = get_or_create_test_event_type()

	def tearDown(self):
		frappe.db.rollback()

	def _create_test_event(self, status="New"):
		doc = frappe.get_doc(
			{
				"doctype": "Event Booking",
				"event_name": "Test Workflow Event",
				"party_type": self.test_party_type,
				"party_name": self.test_party_name,
				"event_type": self.test_event_type,
				"event_date": frappe.utils.add_days(frappe.utils.today(), 7),
				"event_time": "18:00:00",
				"event_location": "Test Venue",
				"booking_status": status,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def test_workflow_exists(self):
		wf = frappe.db.exists("Workflow", {"document_type": "Event Booking"})
		self.assertTrue(wf)

	def test_workflow_states(self):
		wf = frappe.get_doc("Workflow", {"document_type": "Event Booking"})
		states = [s.state for s in wf.states]
		expected = [
			"New",
			"Quoted",
			"Negotiating",
			"Confirmed",
			"In Preparation",
			"Executed",
			"Invoiced",
			"Paid",
			"Cancelled",
		]
		for e in expected:
			self.assertIn(e, states)

	def test_new_to_quoted_transition(self):
		doc = self._create_test_event("New")
		transitions = self._get_allowed_transitions(doc)
		actions = [t.action for t in transitions]
		self.assertIn("Send Quote", actions)
		self.assertIn("Cancel", actions)

	def _get_allowed_transitions(self, doc):
		from frappe.model.workflow import get_transitions

		return get_transitions(doc)
