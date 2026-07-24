# HIOP 1.0.0 interface contract

Status: implemented release candidate.

The React application uses a shared authenticated shell, responsive sidebar/header, real organization identity, session status, light/dark themes, and `#C29F04` as a restrained brand accent. Page routes are lazy-loaded and every data view provides loading, empty/filtered-empty, error, unauthorized/not-found where applicable, and success feedback.

## Pages

- Login: email/password authentication and safe backend/error feedback. Email recovery is not implemented.
- Overview: real inventory availability, recent scans, active tickets, refresh, and ticket links.
- Devices: search, status/department filters, pagination, details, reusable add/edit form, soft retirement, and operational history tabs.
- Network monitor: live summary, device table, approved scan controls, scan state, history, alerts, and WebSocket connection state.
- Alerts: real combined filters, details panel, acknowledgement, related device/ticket navigation, scan/audit context, and live refresh.
- Service tickets: summary, combined filters, pagination, details, reusable create/edit form, assignment, close, supported reopen, and controlled deletion.
- Locations & structure: real normalized hierarchy catalog and admin create/edit/deactivate actions.
- Team & access: real user metrics/table/details/form, role/status/password actions, search, filters, and pagination.
- Audit trail: server-side combined filters, pagination, details, related-record navigation, refresh, and CSV export.
- Reports: six real report datasets, date/filter/sort/pagination controls, charts, cross-navigation, CSV export, and print.
- Settings: validated persisted global settings, organization, hierarchy entry points, scanner, notifications, theme, security facts, health, operations guidance, and application metadata.

## Accessibility and responsive behavior

Controls use native buttons, links, inputs, selects, labels, dialog semantics, ARIA labels where visual text is absent, visible focus treatment, keyboard-operable navigation, and horizontally scrollable tables. Desktop, tablet, and narrow layouts preserve usable navigation and actions. Theme tokens maintain contrast across cards, tables, forms, charts, modals, toasts, and feedback states.

No Version 1.0.0 page exposes fake alerts, reports, health values, save controls, or unsupported actions.
