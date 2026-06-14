import unittest
from unittest.mock import MagicMock, call, patch

from event_bookings.install import (
	_get_first_active_root,
	after_install,
	create_event_coa_accounts,
)
from event_bookings.utils.seed import seed_event_types


@patch("event_bookings.utils.seed.frappe")
class TestSeedEventTypes(unittest.TestCase):
	def test_creates_missing_types(self, mock_frappe):
		mock_frappe.db.exists.return_value = False
		mock_doc = MagicMock()
		mock_frappe.get_doc.return_value = mock_doc

		seed_event_types()

		expected_types = ["Wedding", "Corporate", "Birthday", "Conference", "Private Party"]
		self.assertEqual(mock_frappe.get_doc.call_count, len(expected_types))
		for t in expected_types:
			mock_frappe.get_doc.assert_any_call({"doctype": "Event Type", "type_name": t})
		self.assertEqual(mock_doc.insert.call_count, len(expected_types))
		mock_frappe.db.commit.assert_called_once()

	def test_skips_existing_types(self, mock_frappe):
		mock_frappe.db.exists.return_value = True

		seed_event_types()

		mock_frappe.get_doc.assert_not_called()
		mock_frappe.db.commit.assert_called_once()

	def test_creates_only_missing_types(self, mock_frappe):
		def exists_side_effect(doctype, name):
			return name in ("Wedding", "Corporate")

		mock_frappe.db.exists.side_effect = exists_side_effect
		mock_doc = MagicMock()
		mock_frappe.get_doc.return_value = mock_doc

		seed_event_types()

		self.assertEqual(mock_frappe.get_doc.call_count, 3)


@patch("event_bookings.install.frappe")
class TestCreateEventCoaAccounts(unittest.TestCase):
	def test_creates_accounts_for_each_company(self, mock_frappe):
		mock_frappe.get_all.return_value = ["Test Co"]

		def get_value_side_effect(doctype, filters_or_name, field=None, **kwargs):
			if doctype == "Account":
				root_type = filters_or_name.get("root_type", "")
				if root_type == "Income":
					return "Income - TC"
				if root_type == "Expense":
					return "Expense - TC"
			if doctype == "Company":
				return "TC"
			return None

		mock_frappe.db.get_value.side_effect = get_value_side_effect
		mock_frappe.db.exists.return_value = False
		mock_doc = MagicMock()
		mock_frappe.get_doc.return_value = mock_doc

		create_event_coa_accounts()

		self.assertEqual(mock_frappe.get_doc.call_count, 3)
		mock_frappe.db.commit.assert_called_once()

	def test_skips_existing_accounts(self, mock_frappe):
		mock_frappe.get_all.return_value = ["Test Co"]

		def get_value_side_effect(doctype, filters_or_name, field=None, **kwargs):
			if doctype == "Account":
				root_type = filters_or_name.get("root_type", "")
				if root_type == "Income":
					return "Income - TC"
				if root_type == "Expense":
					return "Expense - TC"
			if doctype == "Company":
				return "TC"
			return None

		mock_frappe.db.get_value.side_effect = get_value_side_effect
		mock_frappe.db.exists.return_value = True

		create_event_coa_accounts()

		mock_frappe.get_doc.assert_not_called()

	def test_logs_error_when_roots_missing(self, mock_frappe):
		mock_frappe.get_all.return_value = ["Bad Co"]
		mock_frappe.db.get_value.return_value = None

		create_event_coa_accounts()

		mock_frappe.log_error.assert_called_once()
		mock_frappe.get_doc.assert_not_called()

	def test_no_companies(self, mock_frappe):
		mock_frappe.get_all.return_value = []
		create_event_coa_accounts()
		mock_frappe.get_doc.assert_not_called()
		mock_frappe.db.commit.assert_called_once()


@patch("event_bookings.install.frappe")
class TestGetFirstActiveRoot(unittest.TestCase):
	def test_queries_correct_filters(self, mock_frappe):
		mock_frappe.db.get_value.return_value = "Income - TC"

		result = _get_first_active_root("Income", "Test Co")

		mock_frappe.db.get_value.assert_called_once_with(
			"Account",
			{"root_type": "Income", "company": "Test Co", "is_group": 1, "disabled": 0},
			"name",
			order_by="lft asc",
		)
		self.assertEqual(result, "Income - TC")

	def test_returns_none_when_not_found(self, mock_frappe):
		mock_frappe.db.get_value.return_value = None
		result = _get_first_active_root("Income", "No Co")
		self.assertIsNone(result)


@patch("event_bookings.install.create_event_coa_accounts")
@patch("event_bookings.install.seed_event_types")
class TestAfterInstall(unittest.TestCase):
	def test_calls_seed_and_coa(self, mock_seed, mock_coa):
		after_install()
		mock_seed.assert_called_once()
		mock_coa.assert_called_once()
