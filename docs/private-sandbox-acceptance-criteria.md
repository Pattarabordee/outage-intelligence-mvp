# Private Sandbox Acceptance Criteria

These criteria define what this public-safe prototype must prove before it is used in a private sandbox pilot discussion. They are not production launch criteria.

## Gate Decision

The current target gate is `ready_for_private_sandbox_discussion`.

The repository can meet that gate when:

- all examples remain synthetic and public-safe
- the partner sandbox flow runs locally without outbound HTTP
- duplicate partner events are idempotent
- duplicate field signals are idempotent
- webhook retry behavior is recorded in the local outbox
- timeout fallback is exercised and auditable
- restoration closure produces ground truth for evaluation
- ML baseline benchmark is available for ETA policy discussion
- pilot data contract and shadow evaluation protocol are available for metric governance discussion
- pilot reports include workflow, metric, sandbox integration, readiness, scenario, ML benchmark, and shadow evaluation evidence
- partner pilot onboarding pack includes checklist, governance boundary, risk register, and go/no-go evidence

## Required Checks

Run the gate commands before using the repo for a pilot walkthrough:

```bash
python scripts/public_safe_scan.py
python scripts/run_partner_sandbox_flow.py
python scripts/run_pilot_scenario_matrix.py
python scripts/run_ml_baseline_benchmark.py
python scripts/run_shadow_evaluation_protocol.py
python scripts/generate_readiness_gate.py
python scripts/generate_partner_pilot_pack.py
python scripts/generate_pilot_report.py --format markdown
```

Expected result:

- `public_safe_scan.status` is `passed`
- `readiness.sandbox_pilot_ready` is `true`
- `readiness.production_ready` is `false`
- `sandbox_integration.outbound_http_sent` is `false`
- `sandbox_integration.flow_coverage_rate` is `1.0`
- `scenario_matrix.failed` is `0`
- `ml_baseline.benchmark_ready` is `true`
- `ml_baseline.no_model_deployed` is `true`
- `shadow_evaluation.shadow_evaluation_ready` is `true`
- `shadow_evaluation.required_field_coverage` is `1.0`
- `pack_ready` is `true`
- `readiness_decision.production_ready` is `false`

## Go Criteria

Use the prototype for private sandbox discussion when:

- API behavior is repeatable from a clean checkout
- incident creation, ETA revision, timeout fallback, restoration, and local retry behavior are covered
- pilot scenario matrix passes all synthetic cases
- ML baseline benchmark compares the rules-first ETA policy against simple statistical baselines
- shadow evaluation validates the pilot data contract on a larger synthetic dataset
- partner pilot onboarding pack makes owners, governance inputs, risks, and production gaps explicit
- generated reports exclude private delivery headers, raw field text, network targets, and operational topology
- known production gaps are visible and not hidden as "ready"

## No-Go Criteria

Do not treat the prototype as production-ready if any of these are true:

- public-safe scan reports unresolved issues
- sandbox flow cannot prove duplicate handling
- timeout fallback is not exercised
- restoration closure does not produce closed-loop data
- ML benchmark output is missing, below minimum rows, or implies deployed model behavior
- shadow evaluation output is missing, fails contract coverage, or implies operational automation
- partner pilot pack is missing, hides governance gaps, or lacks go/no-go criteria
- reports imply live partner integration or operational deployment
- generated output includes real partner data, network targets, raw operational text, or private auth material

## Production Gaps

Before live use, a separate private implementation would still need:

- production authorization policy
- managed database and migration plan
- managed outbound delivery worker
- receiver-side verification
- replay-window enforcement
- live observability and alert routing
- operational data governance review
