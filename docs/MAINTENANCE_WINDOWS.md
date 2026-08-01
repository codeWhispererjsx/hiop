# Maintenance Windows

Maintenance calendars and windows support corporate or property scope, IANA timezone names, standard, recurring, emergency, and blackout periods, approval records, and overlap conflicts. End time must follow start time. Corporate windows are checked against all overlapping approved/scheduled windows; property windows are checked against corporate and same-property windows.

Conflict detection records evidence and severity rather than silently changing a schedule. RFC scheduling validates its interval against an approved linked window. External calendar synchronization is intentionally an adapter boundary; the current scheduled reconciliation validates HIOP's internal calendar only.
