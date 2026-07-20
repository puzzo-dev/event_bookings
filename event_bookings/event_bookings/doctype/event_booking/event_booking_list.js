frappe.listview_settings["Event Booking"] = {
	get_indicator: function (doc) {
		const colors = {
			"New": "blue",
			"Quoted": "blue",
			"Negotiating": "orange",
			"Confirmed": "blue",
			"In Preparation": "blue",
			"Executed": "gray",
			"Invoiced": "green",
			"Paid": "green",
			"Cancelled": "red",
		};
		return [__(doc.booking_status), colors[doc.booking_status] || "gray"];
	},
};
