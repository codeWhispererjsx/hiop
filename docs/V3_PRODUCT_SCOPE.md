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

## Removed specialist capabilities

The standalone pages and public APIs for the following specialist systems were removed from the active V3 product surface:

- analytics, executive BI, and corporate dashboards;
- asset procurement, vendor, contract, and financial lifecycle workspaces;
- CMDB internals and configuration compliance;
- change, problem, RCA, and KEDB specialist workspaces;
- SNMP credentials, topology engineering, Active Directory, and import internals;
- organization hierarchy and multi-property policy administration;
- reports, audit records, and knowledge administration.

Schema migrations and database models remain for upgrade compatibility. A future capability should be surfaced contextually from one of the five pillars rather than restored as a competing top-level module.

## Fresh-start reset

`backend/scripts/reset_operational_data.py` provides an explicit, guarded reset for development or pre-production environments. It previews affected rows by default. Execution requires `--confirm RESET-HIOP-DATA`. Login accounts, system settings, migration state, and required reference catalogs are preserved.
