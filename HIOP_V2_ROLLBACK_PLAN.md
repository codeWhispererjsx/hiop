# HIOP v2 Rollback Plan

## Status

**Procedure documented; execution not verified.** Final release must wait for a successful staging drill.

## Application rollback

Stop traffic, preserve logs, redeploy the previously approved application image, and verify health/authentication before reopening traffic. Never force-push or rewrite Git history.

## Database strategy

Prefer forward-fix for additive migrations. If a tested restore is required, stop writes, restore the protected pre-release backup into a replacement database, point the prior application at it, and verify authentication plus read-only module checks. Do not run downgrade against production data without an approved incident plan.

Import, discovery, AD reconciliation, SNMP onboarding, topology history, analytics evidence, audit logs, and ticket history must remain protected by backup and explicit retention rules.

## Abort conditions

Abort rollout for migration failure, data loss, unauthorized mutation, secret exposure, duplicate scheduler ownership, broken authentication, or failed restore verification. Record the incident and preserve evidence.
