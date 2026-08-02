# Discovery Pipeline

The ordered stages are ICMP reachability, ARP resolution, reverse DNS, hostname resolution, MAC collection, MAC vendor identification, port discovery, service fingerprinting, SNMP, NetBIOS, Windows WMI, Linux SSH, HTTP/HTTPS, TLS certificates, LLDP/CDP topology, DHCP leases, Active Directory correlation, CMDB correlation, confidence calculation, and Configuration Item update.

Each stage is independently persisted, executable, and retryable. Credentialed stages require both policy opt-in and an enabled scoped credential. Evidence records retain source, value, normalization, verification, timestamp, expiry, and weight. Repeated enrichment accumulates unique evidence rather than replacing earlier confidence contributions.

Confidence contributions are ping 15, MAC 15, vendor 10, hostname 10, SNMP 20, AD 10, CMDB 10, LLDP 5, service fingerprint 5, and operating system 10. Unique available evidence is summed and capped at 100, with every contribution stored.
