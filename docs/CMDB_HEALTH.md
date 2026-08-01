# CMDB Health

The deterministic health score evaluates verification freshness, orphan relationships, duplicate candidates, missing owners, relationship completeness, and discovery coverage. Scores range from 0 to 100 and preserve component counts and calculation time.

A CI verified more than 30 days ago becomes stale during scheduled verification. Orphans have no active reviewed relationship. Duplicate counts come from pending exact/strong reconciliation evidence. Unknown or missing data reduces quality; it is never counted as healthy. Historical snapshots support trend reporting without rewriting prior results.
