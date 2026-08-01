# CI Relationships

Relationship types define direction, inverse label, and cardinality. Seeded types include Runs On, Hosts, Depends On, Connected To, Backs Up, Uses, Managed By, Contained In, Located In, Replicates To, Redundant With, Monitored By, Supports, and Owned By.

Every relationship requires source CI, target CI, type, evidence, confidence, and actor. Self-links and duplicates are rejected. Property-crossing containment/location links are rejected. Suppression preserves relationship history; it does not delete evidence. Dependency traversal is bounded, cycle-safe, and limited to dependency-compatible relationship types. Graph snapshots retain checksums and identifiers for audit comparison.
