# Enterprise Knowledge Search

HIOP search is deterministic and uses stored text and metadata only. It covers knowledge articles, runbooks, SOPs, documents, and troubleshooting guides. Article search includes title, summary, body, category, and tags, with filters for property, department, status, category, tag, author, and dates where supported.

Supported ordering is relevance, newest, most viewed, highest rated, and recently updated. Responses are paginated and bounded. PostgreSQL deployments receive GIN full-text indexes; other supported test databases use deterministic case-insensitive matching. Search-index maintenance uses `ANALYZE` and never calls an external or AI search service.

Queries record bounded analytics metadata for unused-content and search-health reporting. No AI summarization, semantic embeddings, inferred answers, or external indexing is used.
