# Enterprise Discovery Engine

Epic 9.5 adds a policy-bounded, auditable discovery engine above HIOP's existing ICMP, ARP, reverse-DNS, SNMP, Active Directory, and topology collectors. A job persists twenty ordered stages. Each stage and per-target task keeps status, attempts, error detail, and retry limits, so partial work can resume.

Administrators authorize private CIDRs, exclusions, maximum hosts, concurrency, timeouts, rate limits, ports, and enabled stages. Manual and scheduled jobs are rejected outside that scope. Credentialed SNMP, SSH, WMI/WinRM, and HTTP inspection is opt-in; intrusive vulnerability tests and exploit techniques are not implemented.

Scheduled jobs queue bounded incremental/full work, refresh local scores and OUI metadata, and flag aging devices. They do not fabricate topology or silently overwrite reviewed CIs.

Manual jobs execute immediately after creation. Existing pending or failed jobs expose **Run now**. The runner now orchestrates policy-authorized ICMP, local ARP, forward-confirmed DNS, unicast NetBIOS, allowlisted service/HTTP/TLS fingerprints, SNMP identity and ENTITY-MIB inventory, imported DHCP leases, synchronized AD computer objects, opt-in WinRM/SSH inventory, reviewed LLDP/CDP topology, confidence, and CMDB correlation.

SNMP configuration and credential testing reuse the canonical **SNMP Monitoring** credential and target pages. This prevents duplicate secrets and ensures the same target authorization, retry, timeout, rate, and audit controls are applied everywhere.
