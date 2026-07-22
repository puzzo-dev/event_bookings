frappe.listview_settings["Event Booking"] = {
	formatters: {
		booking_status: function (value) {
			const color = {
				"New": "blue",
				"Quoted": "blue",
				"Negotiating": "orange",
				"Confirmed": "blue",
				"In Preparation": "blue",
				"Executed": "gray",
				"Invoiced": "green",
				"Paid": "green",
				"Cancelled": "red",
			}[value] || "gray";
			const label = frappe.utils.escape_html(value);
			return `<span class="indicator-pill ${color} filterable no-indicator-dot ellipsis" data-filter="booking_status,=,${label}">
				<span class="ellipsis">${__(label)}</span>
			</span>`;
		},
	},
};
