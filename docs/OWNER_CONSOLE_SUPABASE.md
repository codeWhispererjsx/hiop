# HIOP Owner Console on Supabase

The Owner Console is a separate central service for HIOP staff. It is not a
hotel operational database and does not receive device inventory, credentials,
or full discovery evidence.

## Initial setup

1. Create a Supabase project.
2. Run `supabase db push` from this repository to apply the control-plane schema.
3. Set `HIOP_OWNER_BOOTSTRAP_TOKEN` and deploy `owner-bootstrap`.
4. Use the one-time bootstrap token once to create the first Owner account.
5. Configure Supabase Auth redirect URLs for the Owner Console and enable email
   password recovery.
6. Deploy `installation-checkin` with the service-role key kept only in Supabase.

## Desktop data boundary

An activated desktop sends only its installation key, application version,
local-service health, aggregate device and alert totals, and latest scan and
monitoring timestamps. The installation secret is hashed at rest. Check-ins do
not include passwords, SNMP/AD secrets, device-level inventory, raw scan
evidence, or incident detail.

## Recovery

Use Supabase Auth's password reset email flow. Reset links are single-use and
the front end must send users to `/reset-password` after a successful reset.
