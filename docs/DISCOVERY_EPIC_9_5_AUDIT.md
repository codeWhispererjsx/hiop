# Epic 9.5 Discovery Intelligence Audit

## Baseline audit (before this enhancement)

HIOP already contained strong components, but the enterprise runner did not orchestrate them. The baseline had real ICMP, local ARP, reverse DNS, encrypted SNMP v2c/v3 credentials, bounded SNMP polling, AD synchronization, CMDB matching, and reviewed LLDP/CDP topology services. Discovery Intelligence persisted the twenty-stage job model, evidence, fingerprints, confidence, review states, and CMDB synchronization.

The operational gap was material: the **Run discovery** path called only the legacy reachability scanner. SNMP, service banners, TLS, AD, DHCP, WinRM/SSH, and topology stages were generally marked skipped, so most rows remained IP-centric at 15% confidence. Confidence was also recalculated from only the newest ingest batch rather than all retained evidence.

## Implemented in this integration pass

| Capability | Current implementation |
| --- | --- |
| ICMP / ARP | Existing bounded collectors retained and orchestrated. |
| DNS | PTR candidates now require forward confirmation before becoming verified canonical-hostname evidence. |
| NetBIOS | Bounded unicast node-status lookup; no broadcast or enumeration. |
| SNMP | Existing encrypted v2c/v3 targets are used by Discovery Intelligence. `sysName`, `sysDescr`, `sysObjectID`, uptime, ENTITY-MIB manufacturer/model/serial/firmware, target profile vendor/type, retries, timeout, and authorization checks enrich results. |
| DHCP | Audited lease-import API and persistent correlation table; lease hostname/MAC becomes verified evidence. |
| Active Directory | Correlates synchronized computer objects and enriches canonical name, Windows OS, and version without contacting AD during every scan. Ambiguous matches remain unresolved. |
| Services | Allowlisted, bounded TCP availability and small banners only. HTTP `HEAD` headers and TLS certificate identity/expiry are captured. No vulnerability probes are present. |
| Windows / Linux | Opt-in encrypted credentials use fixed read-only WinRM PowerShell or SSH commands. Arbitrary commands are not accepted from API requests. |
| Topology | Existing LLDP/CDP SNMP collection is invoked inside the authorized policy scope and continues to stage provisional nodes/links for review. |
| Confidence | Scores now accumulate across all unique retained evidence and show every weighted contribution. |
| UI | Device name is the primary field; type, vendor, OS, IP, confidence, review state, last seen, CMDB action, and evidence-contribution cards are visible. |

## Deliberate production safeguards

- Credentialed discovery requires both a policy opt-in and an enabled, scoped credential/target.
- SNMP credentials and target testing remain centralized under **SNMP Monitoring** so secrets are not duplicated.
- SSH rejects unknown host keys. WinRM TLS validates server certificates.
- Service checks are restricted to the policy's approved ports and small response limits.
- LLDP/CDP observations create provisional topology only; administrators retain approval authority.
- Discovery generates CMDB/change suggestions but does not silently approve changes.

## Remaining operational dependencies

Identification quality depends on infrastructure evidence. Network devices must expose read-only SNMP, Windows devices need WinRM/WMI access, Linux devices need a least-privilege SSH account, DNS/DHCP/AD data must be accurate, and VLAN/firewall rules must allow the approved management traffic. A host that exposes only ICMP will correctly remain low-confidence; HIOP does not invent a hostname or vendor.

Direct collection of switch DHCP tables is vendor-specific. This release provides a deterministic audited lease-import contract; DHCP connector adapters can feed that contract without changing correlation behavior.
