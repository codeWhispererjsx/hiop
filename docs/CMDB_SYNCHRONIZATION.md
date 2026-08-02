# Discovery to CMDB Synchronization

Discovery results create or update Configuration Items only through the protected synchronization action. Ignored, false-positive, duplicate, and retired results are blocked. Matching checks the existing result link and normalized MAC identifiers before creating a CI, avoiding IP-only duplication.

New CIs receive a discovery class/type, source reference, state, manufacturer, discovery timestamp, and identifier evidence. Configuration snapshots are checksummed; changed hardware or software can be retained as a proposed change for human review, never implemented automatically.
