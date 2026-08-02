# Enterprise Discovery Engine

Epic 9.5 adds a policy-bounded, auditable discovery engine above HIOP's existing ICMP, ARP, reverse-DNS, SNMP, Active Directory, and topology collectors. A job persists twenty ordered stages. Each stage and per-target task keeps status, attempts, error detail, and retry limits, so partial work can resume.

Administrators authorize private CIDRs, exclusions, maximum hosts, concurrency, timeouts, rate limits, ports, and enabled stages. Manual and scheduled jobs are rejected outside that scope. Credentialed SNMP, SSH, WMI/WinRM, and HTTP inspection is opt-in; intrusive vulnerability tests and exploit techniques are not implemented.

Scheduled jobs queue bounded incremental/full work, refresh local scores and OUI metadata, and flag aging devices. They do not fabricate topology or silently overwrite reviewed CIs.
