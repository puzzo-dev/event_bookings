# Operations portal — design

Frappe-ui style business-owner portal for the event_bookings app (events, retail "Adun", production).
Design Artifact: https://claude.ai/artifact/Pu446kFU99TMXmTTeN7ajt (page "events").

- `*.dc.html` — one file per screen (`Ev*` events, `Rt*` retail/production). Lists link to their own detail pages; detail pages use content (left) + details/attachments (right) with working tabs.
- `canvas.json` — board positions and `is_interactive` flags.
- Cross-board demo state is kept in localStorage (`opsView`, `opsSel_*`, `opsMoved`, `opsTheme`, `opsPacked`).
- The design runtime (`support.js`) is not included; it comes from the Artifact.
