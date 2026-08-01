# Knowledge Base

HIOP Epic 3D provides a property-aware, deterministic knowledge repository. Articles use Markdown as stored source and support categories, tags, comments, ratings, favorites, bounded attachment metadata, view history, revisions, approvals, and related operational records.

## Lifecycle and revisions

The enforced lifecycle is `draft -> in_review -> approved -> published -> archived`. Contributors may draft and submit; administrators publish and archive. A revision snapshot and SHA-256 checksum preserve each reviewed edit. Rollback never mutates history: it creates a new draft based on the selected revision.

Publishing and archiving can be scheduled. Review dates feed the outdated-content queue and reminder job. Article bodies reject executable or embedded markup and are rendered as text/Markdown data, not trusted HTML.

## Scope and access

Corporate records require an administrator. Property records are filtered through existing property access. Admins and superadmins act as knowledge administrators/publishers, technicians as contributors/reviewers, and viewers as readers. The backend remains authoritative.

Attachments store metadata and controlled storage references only. References must be relative and traversal-free; supported types and size are bounded. Secrets and executable content are not accepted.

## Operations

The `/api/v1/knowledge` API exposes dashboard, article, revision, approval, rating, favorite, relationship, report, and export resources. Audit entries are written for privileged mutations. Stable scheduler jobs handle lifecycle dates, expiry, review queues, broken-link validation, statistics, and PostgreSQL index maintenance.

Known limitation: binary upload transport and rich Office/PDF rendering remain the responsibility of the deployment's approved object-storage and preview integration; Epic 3D stores secure document metadata and version references.
