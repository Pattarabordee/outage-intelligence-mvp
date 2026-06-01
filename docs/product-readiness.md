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
- Operator priority and next-step labels for private pilot discussion
- Private pilot evidence report and success metric definitions
- Repeatable partner sandbox integration flow with idempotency, retry, timeout, and restoration proof
- Private sandbox readiness gate with public-safe scan and go/no-go checks
- Pilot scenario matrix for repeatable benchmark coverage across core private pilot risks
- ML baseline benchmark comparing rules-first ETA against simple statistical baselines
- Pilot data contract and shadow evaluation protocol for measuring ETA quality without operational impact
- Partner pilot onboarding and governance pack with checklist, RACI, risk register, and go/no-go criteria
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
2. Use the executive and operator demo surfaces to align the private pilot workflow.
3. Run the partner sandbox integration flow to prove retry-safe behavior locally.
4. Run the pilot scenario matrix to prove repeatable coverage across outage, retry, timeout, restore, and scope-control cases.
5. Run the ML baseline benchmark to measure the current rules-first ETA policy against simple statistical baselines.
6. Run the shadow evaluation protocol to validate the pilot data contract and benchmark on a larger synthetic dataset.
7. Run the readiness gate and review acceptance criteria before any private sandbox discussion.
8. Generate the partner pilot onboarding pack to align owners, governance boundaries, risks, and go/no-go criteria.
9. Generate the private pilot evidence report and agree on success metrics.
10. Build a private pilot service with authentication, tenant boundaries, and partner sandbox payloads.
11. Run side-by-side evaluation against historical synthetic or de-identified incidents.
12. Promote only explainable, measured policy changes into operational workflows.
