# Lagos Continental controlled pilot

## Release decision

HIOP may enter a controlled, read-only pilot only after every blocking item in this document is signed off. A passing application test suite is necessary but does not authorize network access.

## Required operator inputs

Record these outside Git in the approved deployment/secrets system:

- Persistent backend hostname and PostgreSQL service.
- Vercel or other HTTPS frontend hostname.
- Rotated Resend/SMTP credential and a verified sender address. Any key previously pasted into chat must be revoked and replaced.
- Encrypted off-host backup destination and isolated restore-drill database.
- Monitoring and security-log destination.
- Exact pilot property and accountable Lagos Continental IT owner.
- Written list of approved pilot CIDRs and explicit exclusions.
- Read-only SNMPv3, DNS, DHCP, or Active Directory access approved by the hotel.

Do not guess any CIDR, hostname convention, credential, department, room, or production contact.

## Deployment gate

1. Copy `backend/.env.production.example` to a protected location outside the repository and provide real values.
2. Run `python scripts/check-production-readiness.py --env-file <protected-env-file>` and resolve every `FAIL`.
3. Build the immutable backend and frontend images. Confirm the backend image contains `pg_dump` and `pg_restore`.
4. Run the migration job against an isolated restored copy first, then create a verified backup before the production migration.
5. Start exactly one backend process while the embedded scheduler is enabled.
6. Confirm backend `/health` and `/healthz`, frontend `/healthz`, login, authenticated WebSocket connectivity, and centralized log ingestion.
7. Run one manual backup, verify its checksum, copy it off-host, and complete an isolated restore drill.
8. Enroll one property-bound local agent over trusted HTTPS. Confirm its identity cannot submit data for another property.

## Network pilot gate

1. Keep discovery, automatic scanning, automatic alerts, and automatic ticket creation disabled initially.
2. Enter only the written, approved test CIDR in Administration. Add infrastructure-management, payment, life-safety, guest, and other excluded ranges before enabling discovery.
3. Begin with one small non-critical VLAN or subnet and a conservative host limit.
4. Use ICMP/DNS first. Enable SNMP only with approved read-only SNMPv3 credentials. Do not enable SNMPv1 in production.
5. Run one manual discovery and review every result before enabling a schedule.
6. Confirm technical hostname, friendly name evidence, confidence, property, department, and location. Reject unsupported classifications.
7. Confirm no packets were sent outside the approved CIDR and no configuration-changing operation exists.

## Functional acceptance

- Discovery creates or enriches records without duplicates.
- Monitoring reflects real evidence and reports unknown when evidence is absent.
- Alerts remain separate from tickets; approved automation creates a single deduplicated ticket.
- Existing and automatic tickets can be assigned only to active technicians with property access.
- Viewer, technician, property administrator, organization administrator, and platform administrator permissions behave as documented.
- Cross-organization and cross-property direct API attempts return denial.
- Audit events identify the authenticated actor, organization, property, action, and timestamp.
- Backup, restore drill, email verification, invitation, and password recovery are verified.

## Rollback and stop conditions

Stop the pilot immediately for cross-scope access, scans outside the approved CIDR, unexplained network load, repeated duplicate records, credential exposure, missing audit evidence, or database integrity errors. Disable discovery and the local agent, preserve logs and audit history, and revert the application image. Do not reset or delete the database.

## Approval record

The deployment owner, Lagos Continental IT owner, approved CIDRs, excluded ranges, pilot window, rollback owner, backup evidence, restore evidence, and final go/no-go decision must be recorded in the hotel change process before activation.
