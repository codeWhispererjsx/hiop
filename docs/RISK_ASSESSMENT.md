# Change Risk Assessment

Risk calculation is deterministic and auditable. Ten required factors—guest, revenue, operational, security, compliance, downtime, rollback complexity, service dependencies, vendor dependency, and maintenance duration—are scored from 0 through 5. The unweighted total maps to:

- Low: 0–12
- Medium: 13–25
- High: 26–39
- Critical: 40–50

Every assessment stores its factor evidence, rationale, version, actor, and time. Unsupported, missing, or out-of-range factors are rejected. Risk scores inform human review; they never approve or execute a change.
