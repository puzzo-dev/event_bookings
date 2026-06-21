__version__ = "15.0.37"

# ── Monkey-patch: graceful fiscal-year fallback ────────────────────────
# erpnext.accounts.utils.get_fiscal_years raises FiscalYearError when
# the requested date is outside any active Fiscal Year.  Charts then
# crash with an unhandled exception and the browser gets an empty
# response.  This patch catches the error and returns the most recent
# active fiscal year so the chart can render.
# ──────────────────────────────────────────────────────────────────────
import frappe


def _patch_get_fiscal_years():
	try:
		from erpnext.accounts.utils import get_fiscal_years as _orig, FiscalYearError
	except Exception:
		return  # erpnext not installed / not yet loaded

	if getattr(_orig, "_eb_patched", False):
		return  # already patched

	def _patched(*args, **kwargs):
		try:
			return _orig(*args, **kwargs)
		except FiscalYearError:
			# Return the most recent active fiscal year as fallback
			fy = frappe.get_all(
				"Fiscal Year",
				filters={"disabled": 0},
				fields=["name", "year_start_date", "year_end_date"],
				order_by="year_start_date desc",
				limit=1,
			)
			if fy:
				return ((fy[0].name, fy[0].year_start_date, fy[0].year_end_date),)
			# No fiscal years at all — re-raise so callers know
			raise

	_patched._eb_patched = True
	import erpnext.accounts.utils

	erpnext.accounts.utils.get_fiscal_years = _patched


_patch_get_fiscal_years()
