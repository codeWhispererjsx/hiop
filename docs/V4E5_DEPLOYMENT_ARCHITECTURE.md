# HIOP V4E.5 deployment foundation

HIOP remains a web application. Normal organization configuration is stored in the database and managed through **Administration → Organization**; it does not require Python or React changes.

## Supported application boundary

```text
Browser → HIOP web frontend → authenticated HIOP API → PostgreSQL
                                      ↓
                          discovery/monitoring services
```

An on-premise installation may run all server components inside the hotel network. A future hosted installation may use an organization-bound local agent:

```text
Browser → HIOP cloud/backend → authenticated organization agent → hotel network
```

V4E.5 implements only passive agent identity, organization ownership, status, version and heartbeat timestamps. It does **not** implement network collection, remote command execution, auto-updates, cloud deployment, arbitrary scripts, or a distribution channel.

## Security boundary

- Every department, location, assignment and agent lookup is resolved through the authenticated organization context.
- Platform administrators must explicitly select an organization context; organization users cannot override theirs.
- A future agent credential must be bound server-side to one organization and must never accept an organization ID from an untrusted payload as authority.
- The eventual collection channel should be outbound, mutually authenticated, least-privilege and read-only by default.

## Future agent interface

The stable boundary is: register identity, authenticate, submit heartbeat, then submit typed read-only observations. Observation ingestion and agent credentials are intentionally deferred; no remote execution interface should be added to this foundation.
