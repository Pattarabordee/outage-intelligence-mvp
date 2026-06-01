# Private Pilot Transition Gates

These gates define how the project should move from public prototype to private sandbox, private pilot, and eventually production. They are intentionally strict so the prototype does not get mistaken for a live service.

## Gate 1: Public Prototype

Pass this gate when:

- tests and coverage pass
- public-safe scan passes
- sandbox flow proves idempotency, timeout fallback, restoration closure, and local retry behavior
- scenario matrix passes all synthetic cases
- onboarding pack and risk register are available

Expected decision: `ready_for_private_sandbox_discussion`

## Gate 2: Private Sandbox

Pass this gate when:

- pilot owners are assigned
- partner class and synthetic site scope are agreed
- private access boundary is designed
- data minimization and retention expectations are reviewed
- workflow evidence can be generated without operational data
- rollback and pause procedure are documented

Expected decision: `ready_for_private_pilot_build`

## Gate 3: Private Pilot

Pass this gate when:

- partner-scoped authorization is implemented
- tenant and site-scope policy is enforced
- managed delivery worker is tested
- audit access review is active
- alert routing and owner rotation are defined
- shadow evaluation runs on governed pilot rows without changing partner-facing decisions

Expected decision: `ready_for_controlled_partner_pilot`

## Gate 4: Production

Production requires a separate review. Do not infer production readiness from sandbox or pilot success.

Production needs:

- production authorization and tenant policy
- managed database and migration strategy
- service objectives and live alert routing
- release automation and rollback verification
- support ownership and incident response runbooks
- approved data governance and recurring audit

Expected decision: `requires_separate_production_readiness_review`
