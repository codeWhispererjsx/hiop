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
