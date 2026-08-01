# CMDB Discovery Reconciliation

Reconciliation adapters currently prepare candidates from Device Inventory and legacy Network Discovery. Device matches prioritize explicit asset links, then exact serial identity. Discovery matches prioritize explicit discovery links and reviewed device links. IP alone is not accepted as guaranteed identity.

Refreshing reconciliation creates or updates candidates only. Administrators explicitly choose create, link, reject, or ignore. Creating requires a valid CI class/type; linking requires an existing proposed CI. Source evidence, score, conflicts, reviewer, and timestamp remain recorded. SNMP, Active Directory, configuration, and CSV sources use the same candidate contract as their property-aware adapters are connected.
