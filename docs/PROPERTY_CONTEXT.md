# Property context

Epic 1C establishes property context inside one HIOP organization. The backend
resolves `X-HIOP-Property-ID`, validates that the authenticated user may access
the active property, and exposes the result through `GET /api/v1/context`.

Global administrators may view active properties. Other users receive access
through `user_property_access` assignments with property viewer, technician, or
administrator levels. Disabled and expired assignments are rejected. The
frontend stores only the selected property identifier and sends it as a header;
authorization remains backend-enforced.

The migration is additive. Existing records remain readable and nullable
property context is intentionally preserved for a later reviewed legacy-data
assignment workflow. This phase does not implement SaaS tenancy or automatic
cross-property reassignment.
