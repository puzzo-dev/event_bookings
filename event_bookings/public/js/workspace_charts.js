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
	const now = frappe.datetime.nowdate();
	// Trends are measured by booking_date over the past 12 months.
	// NOTE: frappe.datetime.month_start() ignores arguments and returns
	// the *current* month's start as ISO datetime (unsuitable for Date
	// controls).  Build YYYY-MM-DD manually from add_months result.
	const first_day = frappe.datetime.add_months(now, -11).substring(0, 7) + '-01';
	const last_day = now;

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
		label: __('From Date'),
		fieldname: 'from_date',
		fieldtype: 'Date',
		default: first_day,
		reqd: 1
	});

	fields.push({
		label: __('To Date'),
		fieldname: 'to_date',
		fieldtype: 'Date',
		default: last_day,
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

// ── Bootstrap ──────────────────────────────────────────────────────────
frappe.router.on('change', init_chart_filters);
