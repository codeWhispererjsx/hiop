# HIOP V3-ADMIN — Operational Access Control & Administration

## Status

V3-ADMIN STATUS: Complete

## Existing users preserved

- Users: 2
- Active: 2
- Inactive: 0
- `admin`: active, migrated from legacy `admin` to `superadmin`
- `joe`: active, migrated from legacy `admin` to `superadmin`

Both existing IDs, usernames, emails, password hashes, active states, creation dates, and relationships were preserved. No credentials were reset, no users were recreated, and no user was deleted. Legacy `admin` represented the highest application privilege, so mapping those accounts to explicit `superadmin` preserves rather than reduces their access.

## Roles

- Super Administrator: full administration and operational access
- IT Administrator: operational administration and management of Technician/Viewer accounts only
- IT Technician: normal discovery and incident operations without user/role/settings administration
- Viewer: read-only operational visibility

The policy is deliberately static and small. No dynamic enterprise permission engine or duplicate roles/permissions tables were introduced.

## Authorization and escalation

- Backend role checks recognize Super Administrator as the highest role.
- IT Administrators cannot create or manage administrator accounts and can assign only Technician or Viewer.
- Users cannot change their own role.
- Technician and Viewer role changes are rejected with 403.
- Inactive users cannot authenticate or continue using an existing token.
- The last active Super Administrator cannot be deactivated or demoted.
- User deletion remains a compatibility route that performs safe deactivation.
- Unauthenticated role-change API validation returned 401; automated authenticated insufficient-role cases return 403.

## Audit

User creation, profile updates, activation, deactivation, role changes, password resets, and successful authentication use the existing audit table and authenticated actor. The Administration page shows actual recent audit events only to Super Administrators.

## Migration

Migration `v3admin9e1f3a5b7` is applied at Alembic head. It adds `users.last_login_at` and maps legacy role labels without resetting the database or modifying credentials. Existing 78 audit records and 8 inventory devices remain present.

## UI

- New `/administration` checkpoint links Users and existing Settings.
- Four role definitions and permissions are visible and understandable.
- Full audit visibility is Super Administrator-only.
- Administration navigation is hidden from Technician and Viewer.
- Role change and deactivation require confirmation; self-role change is hidden.
- Viewer discovery and incident-creation controls are removed; read-only evidence remains visible.
- Inventory edit/create controls require Administrator or Super Administrator.

## Tests

- Backend: 177 passed
- Frontend: 39 passed
- Lint: passed
- Production build: passed
- Migration: `v3admin9e1f3a5b7 (head)`

## Browser validation

Pending role-by-role authenticated validation. The running application and sign-in page rendered successfully, but account passwords were not available to this task and were intentionally not reset. Automated backend tests cover Super Administrator, IT Administrator, Technician, Viewer, inactive authentication, self-escalation, cross-role escalation, audit attribution, and direct API rejection.

## Known limitations

- No Technician or Viewer account currently exists in the live database, so their live browser sessions cannot be demonstrated without authorization to create test accounts.
- `last_login_at` begins empty and is populated on the next successful sign-in.
- IT Technician incident assignment ownership continues to use the existing incident model; this checkpoint does not add enterprise row-level authorization infrastructure.

## Not implemented

V3D, V3E, V3F, advanced monitoring, alerts/events, impact analysis, CMDB, procurement, vendor management, SSO/LDAP/Entra federation, multi-property administration, dynamic enterprise IAM, or authentication redesign.

## Git

- Commit: not created
- Pushed: No
