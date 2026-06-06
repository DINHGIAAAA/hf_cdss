# Audit

Stores input, context, output, verification results, and case-level audit trail.

PostgreSQL stores append-only `recommendation_created` and `verification_completed`
events in `cdss_audit_events`. Audit failures are logged but never block clinical output.
