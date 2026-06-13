EVENT_BOOKING_CONFIRMATION_HTML = """
<div style="font-family: sans-serif; padding: 20px;">
    <h2 style="text-align: center; color: #333;">Event Booking Confirmation</h2>
    <hr>

    <table style="width: 100%; margin-bottom: 20px;">
        <tr>
            <td style="width: 50%;">
                <strong>Booking ID:</strong> {{ doc.name }}<br>
                <strong>Event Name:</strong> {{ doc.event_name }}<br>
                <strong>Date:</strong> {{ doc.get_formatted("event_date") }}<br>
                <strong>Time:</strong> {{ doc.event_time }}
            </td>
            <td style="width: 50%; text-align: right;">
                <strong>Status:</strong> {{ doc.booking_status }}<br>
                <strong>Customer:</strong> {{ doc.customer }}<br>
                <strong>Location:</strong> {{ doc.event_location }}
            </td>
        </tr>
    </table>

    {% if doc.sales_order %}
        <h4 style="border-bottom: 1px solid #ccc; padding-bottom: 5px;">Services Requested</h4>
        {% set so = frappe.get_doc("Sales Order", doc.sales_order) %}
        <table class="table table-bordered" style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
            <thead>
                <tr style="background-color: #f9f9f9;">
                    <th style="padding: 8px; border: 1px solid #ddd;">Item</th>
                    <th style="padding: 8px; border: 1px solid #ddd; text-align: right;">Qty</th>
                    <th style="padding: 8px; border: 1px solid #ddd; text-align: right;">Rate</th>
                    <th style="padding: 8px; border: 1px solid #ddd; text-align: right;">Amount</th>
                </tr>
            </thead>
            <tbody>
                {% for item in so.items %}
                <tr>
                    <td style="padding: 8px; border: 1px solid #ddd;">{{ item.item_name }}</td>
                    <td style="padding: 8px; border: 1px solid #ddd; text-align: right;">{{ item.qty }} {{ item.uom }}</td>
                    <td style="padding: 8px; border: 1px solid #ddd; text-align: right;">{{ item.get_formatted("rate") }}</td>
                    <td style="padding: 8px; border: 1px solid #ddd; text-align: right;">{{ item.get_formatted("amount") }}</td>
                </tr>
                {% endfor %}
            </tbody>
            <tfoot>
                <tr>
                    <td colspan="3" style="padding: 8px; border: 1px solid #ddd; text-align: right;"><strong>Estimated Total</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd; text-align: right;"><strong>{{ so.get_formatted("grand_total") }}</strong></td>
                </tr>
            </tfoot>
        </table>
    {% else %}
        <p><em>No services linked yet. (Awaiting Sales Order)</em></p>
    {% endif %}

    <div style="margin-top: 40px; font-size: 0.9em; color: #666; text-align: center;">
        <p>Thank you for booking your event with us. This is an automatically generated confirmation.</p>
    </div>
</div>
"""
