/**
 * Event Bookings — Workspace Chart Filter Popup
 *
 * Injects a "Filter" button into each Dashboard Chart widget on the
 * Event Bookings workspace. Clicking it opens a dialog that lets
 * authorized users edit the underlying report filters.
 */

frappe.provide('event_bookings.workspace');

const CHART_CONFIG = {
	'Event Booking Revenue Trends': {
		default_filters: { period: 'Monthly', based_on: 'Revenue', date_field: 'booking_date' }
	},
	'Event Booking Count Trends': {
		default_filters: { period: 'Monthly', based_on: 'Count', date_field: 'booking_date' }
	},
	'Events By Event Type': {
		default_filters: { based_on: 'Count' },
		hide_period: true,
		hide_date_field: true
	}
};

function init_chart_filters() {
	const route = frappe.get_route && frappe.get_route();
	if (!route || !route.length) return;
	if (route[0] !== 'workspace') return;
	if (route[1] !== 'event-bookings') return;

	// Wait for widgets to render
	setTimeout(() => {
		inject_filter_buttons();
	}, 1200);

	// Re-inject after workspace refresh
	const original_refresh = frappe.workspace?.page?.refresh;
	if (original_refresh && !frappe.workspace.page._eb_patched) {
		frappe.workspace.page._eb_patched = true;
		frappe.workspace.page.refresh = function (...args) {
			original_refresh.apply(this, args);
			setTimeout(inject_filter_buttons, 800);
		};
	}
}

function inject_filter_buttons() {
	const widgets = document.querySelectorAll('.widget[data-widget-type="chart"]');

	widgets.forEach((widget) => {
		const chartName = widget.getAttribute('data-name');
		if (!chartName || !CHART_CONFIG[chartName]) return;
		if (widget.querySelector('.eb-chart-filter-btn')) return;

		const head = widget.querySelector('.widget-head');
		if (!head) return;

		const btn = document.createElement('button');
		btn.className = 'btn btn-xs btn-default eb-chart-filter-btn';
		btn.title = __('Edit Chart Filters');
		btn.innerHTML = '<i class="fa fa-filter" style="margin-right:4px;"></i>' + __('Filter');
		btn.style.cssText = 'margin-left:6px;padding:2px 8px;font-size:11px;';

		btn.addEventListener('click', (e) => {
			e.stopPropagation();
			open_chart_filter_dialog(chartName);
		});

		head.appendChild(btn);
	});
}

function open_chart_filter_dialog(chart_name) {
	const cfg = CHART_CONFIG[chart_name];

	const fields = [
		{
			label: __('Chart'),
			fieldname: 'chart_name',
			fieldtype: 'Data',
			read_only: 1,
			default: chart_name
		},
		{ fieldtype: 'Section Break', label: __('Filters') }
	];

	if (!cfg.hide_date_field) {
		fields.push({
			label: __('Date Field'),
			fieldname: 'date_field',
			fieldtype: 'Select',
			options: [
				{ label: __('Booking Date'), value: 'booking_date' },
				{ label: __('Event Date'), value: 'event_date' }
			],
			default: cfg.default_filters.date_field || 'booking_date',
			reqd: 1
		});
	}

	if (!cfg.hide_period) {
		fields.push({
			label: __('Period'),
			fieldname: 'period',
			fieldtype: 'Select',
			options: [
				{ label: __('Monthly'), value: 'Monthly' },
				{ label: __('Weekly'), value: 'Weekly' },
				{ label: __('Quarterly'), value: 'Quarterly' },
				{ label: __('Yearly'), value: 'Yearly' }
			],
			default: cfg.default_filters.period || 'Monthly',
			reqd: 1
		});
	}

	fields.push({
		label: __('Based On'),
		fieldname: 'based_on',
		fieldtype: 'Select',
		options: [
			{ label: __('Revenue'), value: 'Revenue' },
			{ label: __('Count'), value: 'Count' }
		],
		default: cfg.default_filters.based_on || 'Count',
		reqd: 1
	});

	fields.push({ fieldtype: 'Column Break' });

	fields.push({
		label: __('Fiscal Year'),
		fieldname: 'fiscal_year',
		fieldtype: 'Link',
		options: 'Fiscal Year',
		default: cfg.default_filters.fiscal_year || erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
		reqd: 1
	});

	if (frappe.boot && frappe.boot.sysdefaults && frappe.boot.sysdefaults.company) {
		fields.push({
			label: __('Company'),
			fieldname: 'company',
			fieldtype: 'Link',
			options: 'Company',
			default: frappe.defaults.get_user_default('Company') || frappe.boot.sysdefaults.company,
			reqd: 1
		});
	}

	let d;
	try {
		d = new frappe.ui.Dialog({
			title: __('Edit Chart Filters'),
			fields: fields,
			primary_action_label: __('Apply'),
			primary_action(values) {
			// Strip read-only helper field
			delete values.chart_name;

			frappe.call({
				method: 'event_bookings.api.workspace.update_chart_filters',
				args: {
					chart_name: chart_name,
					filters: values
				},
				callback(r) {
					if (r.exc) {
						frappe.msgprint(r.exc);
						return;
					}
					frappe.show_alert({
						message: __('Chart filters updated'),
						indicator: 'green'
					});
					d.hide();

					// Reload workspace so charts re-fetch with updated filters
					const route = frappe.get_route && frappe.get_route();
					if (route && route.length >= 2) {
						frappe.set_route('workspace', route[1]);
					}
				}
			});
		}
	});

	// Pre-fill with current stored filters
	frappe.db.get_value('Dashboard Chart', chart_name, 'filters_json')
		.then((r) => {
			if (r.message && r.message.filters_json) {
				try {
					const saved = JSON.parse(r.message.filters_json);
					// Only set fields that exist in the dialog
					const to_set = {};
					fields.forEach((f) => {
						if (f.fieldname && saved[f.fieldname] !== undefined) {
							to_set[f.fieldname] = saved[f.fieldname];
						}
					});
					if (Object.keys(to_set).length) d.set_values(to_set);
				} catch (e) {
					// ignore malformed JSON
				}
			}
		});

	d.show();
	} catch (err) {
		frappe.show_alert({
			message: __('Unable to open chart filter dialog'),
			indicator: 'red'
		});
		console.error('Chart filter dialog error:', err);
	}
}

// ── Fix core ERPNext fiscal-year sync-AJAX hang ───────────────────────
// erpnext.utils.get_fiscal_year uses async: false which freezes the
// browser UI when the requested date is outside any active Fiscal Year.
// This patch skips the blocking server call and falls back to the
// cached current fiscal year.
(function patch_fiscal_year() {
	if (!window.erpnext || !erpnext.utils) return;
	if (erpnext.utils._eb_original_get_fiscal_year) return; // already patched

	erpnext.utils._eb_original_get_fiscal_year = erpnext.utils.get_fiscal_year;
	erpnext.utils.get_fiscal_year = function (date, with_dates = false, boolean = false) {
		if (!frappe.boot.setup_complete) return;

		const today = frappe.datetime.get_today();
		if (!date) date = today;

		let fiscal_year = "";
		if (
			frappe.boot.current_fiscal_year &&
			date >= frappe.boot.current_fiscal_year[1] &&
			date <= frappe.boot.current_fiscal_year[2]
		) {
			fiscal_year = with_dates
				? frappe.boot.current_fiscal_year
				: frappe.boot.current_fiscal_year[0];
		} else if (frappe.boot.current_fiscal_year) {
			// Fallback: return the cached fiscal year instead of making a
			// synchronous AJAX call that will freeze the browser.
			fiscal_year = with_dates
				? frappe.boot.current_fiscal_year
				: frappe.boot.current_fiscal_year[0];
		}
		return fiscal_year;
	};
})();

// ── Fix chart_widget fetch crash leaving widget in broken state ───────
// fetch_and_update_chart has no .catch(), so a server error leaves the
// widget with stale/corrupt data and the filter button hangs on next
// click.  We wrap it so rejections are handled gracefully.
(function patch_chart_fetch() {
	const Widget = frappe.widget ? frappe.widget.chart_widget : null;
	if (!Widget) return;
	const proto = Widget.prototype;
	if (proto._eb_fetch_patched) return;

	proto._eb_fetch_patched = true;
	const orig_fetch = proto.fetch_and_update_chart;
	proto.fetch_and_update_chart = function (...args) {
		const result = orig_fetch.call(this, ...args);
		// orig returns nothing, but the internal Promise may reject.
		// Wrap the internal fetch promise if we can reach it safely.
		return result;
	};

	// More direct: wrap the .fetch() method to add a .catch()
	const orig_fetch_data = proto.fetch;
	proto.fetch = function (filters, refresh, args) {
		const p = orig_fetch_data.call(this, filters, refresh, args);
		if (p && p.catch) {
			p.catch((err) => {
				console.error("Chart fetch failed:", err);
				frappe.show_alert({
					message: __("Chart data failed to load. Reset the chart if this persists."),
					indicator: "red",
				});
				this.loading && this.loading.hide();
				this.empty && this.empty.show();
			});
		}
		return p;
	};
})();

// ── Fix with_doctype hanging when server returns empty/403 ────────────
(function patch_with_doctype() {
	if (!frappe.model || !frappe.model.with_doctype) return;
	if (frappe.model._eb_with_doctype_patched) return;

	frappe.model._eb_with_doctype_patched = true;
	const orig = frappe.model.with_doctype;
	frappe.model.with_doctype = function (doctype, callback, async) {
		const r = orig.call(this, doctype, callback, async);
		if (r && r.catch) {
			r.catch((err) => {
				console.error("with_doctype failed:", doctype, err);
				// Still call callback so the chart/filter dialog isn't blocked
				if (callback) {
					try { callback(); } catch (e) { console.error(e); }
				}
			});
		}
		return r;
	};
})();

// ── Bootstrap ──────────────────────────────────────────────────────────
frappe.router.on('change', init_chart_filters);
