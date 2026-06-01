# Product Readiness Notes

This repository is ready as a public-safe enterprise product prototype. It is not a production deployment.

## Prototype-Ready

- Partner-facing API shape with versioned `/api/v1` routes
- Optional sandbox API-key authentication and partner boundary
- Partner sandbox profiles with synthetic site-scope controls
- Idempotency for incident and field-signal ingestion
- Standardized error response shape
- Audit trail for ETA revisions, timeout fallback, and restoration closure
- Local webhook outbox with signed metadata, retry scheduling, and sandbox delivery attempts
- Executive demo summary feed and public-safe walkthrough page
- Operator pilot console summary feed and public-safe workflow page
- Health endpoint with public-safe service metadata
- Test and coverage gate for core workflows
- Synthetic data boundary and documented governance assumptions

## Production Gaps To Close Before Live Use

- Production-grade authentication and partner authorization
- Strong tenant isolation beyond the local SQLite prototype
- Production partner registry, contract lifecycle, and site authorization source of truth
- Rate limiting and replay protection for write endpoints
- Real outbound webhook delivery workers and receiver-side signature verification
- Database migration strategy beyond local SQLite
- Structured observability, alerting, and incident-owner runbooks
- Production operator dashboard with access control, live telemetry, role-specific filtering, and runbook links
- Data retention, de-identification, and regulatory review for real operational data

## Recommended Rollout Path

1. Keep the current repo as a reference implementation and product demo.
2. Build a private pilot service with authentication, tenant boundaries, and partner sandbox payloads.
3. Run side-by-side evaluation against historical synthetic or de-identified incidents.
4. Promote only explainable, measured policy changes into operational workflows.
