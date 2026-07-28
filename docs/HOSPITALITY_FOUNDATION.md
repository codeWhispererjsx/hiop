# HIOP v3 Hospitality Foundation

HIOP v3.0.0-dev rebrands the product as the **Hospitality IT Operations Platform** while preserving the HIOP acronym, repository, database, environment prefixes, and existing API routes.

## Organization and property hierarchy

`Organization` represents an operator, brand, owner, or hospitality group. `Property` represents a hotel, resort, apartment, conference center, restaurant, or mixed hospitality site. The intended context is:

`Organization → Property → Department → Room → Device`

Existing `properties`, `departments`, and `rooms` tables remain available. Existing properties receive nullable organization context; no default organization is invented. Devices gain nullable `property_id`, preserving all existing device rows and legacy department/location strings.

## API and permissions

Authenticated administrators and technicians can read `/api/v1/organizations` and `/api/v1/properties`. Only administrators can create, update, or archive properties and create organizations. Archive is a safe status transition; it does not delete historical records. Backend RBAC remains authoritative.

## Frontend

The protected `/organizations` and `/properties` pages provide searchable-ready directories, status/type context, basic counts, empty/error states, and administrator-only creation controls. The existing `/hierarchy` route remains compatible. A future property selector can use these APIs; this phase does not introduce multi-tenant isolation or SaaS behavior.

## Migration and compatibility

Migration `f3a4b5c6d7e8` adds organizations, nullable property organization context, hospitality fields, and nullable device property context. Upgrade and downgrade are additive and were exercised safely against the local development database. Existing rows remain valid without a property assignment.

## Explicit exclusions

This foundation does not implement SaaS tenancy, billing, licensing, automation, AI, hotel integrations, mobile applications, configuration backups, or HIOP v3 feature modules beyond domain context.
