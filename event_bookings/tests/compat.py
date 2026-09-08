"""Test base class that works on both Frappe v15 and v16.

v16 removed `frappe.tests.utils` entirely. The DB-backed base class that used
to live there as `FrappeTestCase` is now `frappe.tests.IntegrationTestCase`,
and v15 has no such name — so neither import works on both.

The shim exists so this app stays one codebase across the two branches rather
than a v15 tree and a v16 tree that have to be kept in step by hand. Test
modules import `FrappeTestCase` from here and never from frappe directly.
"""

try:  # Frappe v16 and later
	from frappe.tests import IntegrationTestCase as FrappeTestCase
except ImportError:  # Frappe v15
	from frappe.tests.utils import FrappeTestCase

__all__ = ["FrappeTestCase"]
