# HIOP Enterprise + Hospitality interface contract

Status: implemented for `3.0.0-dev`.

The React application uses a shared authenticated shell, responsive sidebar/header, real organization identity, session status, and instant light/dark themes. Page routes remain lazy-loaded and every data view retains its loading, empty/filtered-empty, error, unauthorized/not-found, and success feedback.

## Design system

`frontend/src/theme/tokens.css` is the only source of literal interface colors. Semantic aliases preserve compatibility with existing module styles while ensuring every page follows the same theme. `frontend/src/styles/design-system.css` provides the shared presentation layer for navigation, headers, cards, buttons, forms, tables, badges, dialogs, notifications, charts, feedback, and responsive behavior.

The official palette is Royal Blue for primary interaction, Navy for enterprise structure, Emerald for positive operational state, and Premium Gold only for hospitality identity or executive emphasis. Status semantics use green, amber, red, sky, slate, violet, and neutral tokens. Color is always paired with visible text, iconography, or status labels.

Typography uses Inter when available and a system UI fallback. The token system defines four font weights, a type hierarchy, a consistent spacing scale, small-to-full radii, elevation levels, focus rings, and named z-index layers. Page-level CSS uses semantic variables rather than independent palettes.

## Theme behavior

Light mode uses the designated cool-gray background, white cards, dark text, and Navy sidebar. Dark mode uses the designated deep-blue background, raised slate cards, near-black sidebar, and high-contrast text. The inline bootstrap applies the saved or operating-system preference before React loads to avoid a theme flash. The Theme provider synchronizes system changes and persists explicit user preference in `localStorage` under `hiop_theme`.

## Component standards

- Primary buttons use Royal Blue; destructive actions remain red; secondary actions use bordered neutral surfaces.
- Inputs, selectors, and text areas share hover, focus, disabled, validation, and placeholder treatment.
- Tables provide sticky headers, row hover, horizontal overflow, readable density, and text-bearing status badges.
- Cards and dashboard panels use soft borders, restrained shadows, consistent radii, and responsive grids.
- Modal focus trapping, keyboard escape, toast live regions, chart text/table alternatives, and visible focus rings remain intact.
- Existing SVG `Icon` is the single icon system; no second icon dependency was introduced.

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

The global reduced-motion rule honors operating-system preference. Mobile layouts keep primary actions full-width where needed, collapse the authenticated shell into the existing drawer navigation, and prevent horizontal overflow on the login experience. Complex data tables retain controlled horizontal scrolling rather than hiding fields.

No Version 1.0.0 page exposes fake alerts, reports, health values, save controls, or unsupported actions.
# Knowledge workspace

`/knowledge` provides responsive subviews for Dashboard, Articles, Runbooks, SOPs, Service Catalog, Documents, Troubleshooting, Checklists, Search, Approvals, Favorites, Recently Viewed, and Reports. The workspace uses existing HIOP panels, cards, forms, feedback, dark/light tokens, responsive grids, and authenticated API/download clients. Markdown is displayed without unsafe HTML injection.

# Change management workspace

`/changes` provides a responsive tabbed workspace for dashboards, RFC register/builder/details, approvals, CAB, deterministic risk, maintenance calendar, execution, releases, timeline, reports, and audit. Mutation controls are hidden for read-only roles while the backend remains authoritative. Empty, loading, and safe error states use the existing HIOP design system.

# CMDB workspace

`/cmdb` provides Dashboard, CI Explorer/detail, reviewed CI creation, Relationship Manager, accessible dependency graph/list, Impact Analysis, Reconciliation, Health, Attribute Manager, Search, and Reports. The visual graph includes a text relationship fallback. Forms use existing tokens and collapse to one column on narrow screens; unauthorized mutation controls remain hidden.
