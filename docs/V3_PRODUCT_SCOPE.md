# HIOP V3 Product Scope

HIOP's everyday interface is organized around five outcomes:

| Pillar | Primary workspace | Purpose |
| --- | --- | --- |
| Discover | Discovery Intelligence | Find and identify network devices. |
| Monitor | Network Monitor | Track availability, health, and alerts. |
| Manage | Devices | Maintain the operational device inventory. |
| Automate | Automation | Run controlled workflows and playbooks. |
| Maintain | Incidents | Restore service and coordinate operational work. |

Administration is available to administrators for product configuration and access control.

## Specialist capabilities

The following implementations remain in the codebase for future integration or direct, authorized use, but are intentionally absent from primary navigation because they are not standalone day-to-day destinations:

- analytics, executive BI, and corporate dashboards;
- asset procurement, vendor, contract, and financial lifecycle workspaces;
- CMDB internals and configuration compliance;
- change, problem, RCA, and KEDB specialist workspaces;
- SNMP credentials, topology engineering, Active Directory, and import internals;
- organization hierarchy and multi-property policy administration;
- reports, audit records, and knowledge administration.

These capabilities should be surfaced contextually from the five pillars when a user needs them. They should not compete with the primary workflow.

## Fresh-start reset

`backend/scripts/reset_operational_data.py` provides an explicit, guarded reset for development or pre-production environments. It previews affected rows by default. Execution requires `--confirm RESET-HIOP-DATA`. Login accounts, system settings, migration state, and required reference catalogs are preserved.
