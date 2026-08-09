# V2A discovery confidence

Confidence is an explainable sum of distinct evidence types, capped at 100. Repeated observations of the same evidence type do not add points.

| Evidence | Weight |
| --- | ---: |
| ICMP response | 15 |
| ARP/DHCP MAC address | 15 |
| DNS-confirmed hostname | 15 |
| DNS resolution attempt/result | 5 |
| DHCP description | 10 |
| OUI vendor match | 10 |
| Hostname rule suggestion | 5 |
| Service fingerprint | 5 |
| Operating-system evidence | 10 |
| SNMP identity | 20 |
| AD correlation | 10 |
| Existing inventory/CMDB correlation | 10 |
| LLDP/CDP evidence | 5 |

Hostname-rule evidence is deliberately low-weight because it is a suggestion, not an independently verified identity. A failed DNS lookup records the attempt/status for auditability but does not create a hostname.

## V2B SNMP enrichment

A successful, read-only SNMP identity response contributes 20 points once, regardless of the number of returned OIDs. Independently agreeing vendor evidence may contribute the existing 10-point vendor weight and an SNMP hostname can contribute the existing hostname weight. Model, serial, firmware, uptime, and interface evidence remain individually traceable but add no standalone points. Therefore an SNMP response cannot produce 100% confidence by itself.

## V2C Active Directory enrichment

An exact AD computer-object match contributes 10 points after normalizing the short hostname, FQDN, and trailing computer-account `$`. Independent agreement contributes 10 points when the AD description exactly matches an existing description, 5 when the AD department suggestion matches the existing department, and 5 when the discovered FQDN agrees with the configured AD domain. AD operating-system and description evidence use the existing 10-point categories and are counted only once when another source already supplied that category.

OU, distinguished name, enabled state, last logon, and other returned attributes remain traceable evidence but add no standalone score. A successful bind or merely responsive directory contributes no confidence, and an AD response never assigns 100% by itself.

## V2D correlation and confidence

Correlation is separate from confidence. A result is permanently correlated only by an agreeing MAC address, existing discovery identity, usable serial number, hostname/computer name, or FQDN, in that priority order. IP address is recorded as supporting evidence and history, but IP alone does not create a permanent correlation.

The existing distinct evidence-type weights remain the base score. Independent sources that report the same MAC or hostname add 10 points per identifier; agreeing descriptions or device types add 5 points each. Agreement bonuses are capped at 20 points. Each unresolved identity conflict subtracts 15 points, capped at a 45-point penalty. Automatically calculated confidence is capped at 95; 100 is possible only after administrator confirmation and with no unresolved conflicts.

The UI uses honest bands rather than implying precision: Low 0–29, Medium 30–59, High 60–84, and Very High 85–100. The stored explanation records the base score, agreement bonus, conflict penalty, confirmation state, evidence types, and agreement categories.
