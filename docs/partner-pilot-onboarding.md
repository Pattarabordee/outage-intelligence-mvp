# Partner Pilot Onboarding

This guide turns the prototype into a private sandbox discussion pack for a utility-to-enterprise outage intelligence pilot. It is a planning artifact, not a production launch plan.

## Capability

The pilot onboarding capability helps a utility team and an enterprise partner align on a controlled sandbox workflow: outage event intake, immediate ETA, field-driven revision, timeout fallback, local retry evidence, restoration closure, and evaluation artifacts.

## Constraints

- All public examples remain synthetic and public-safe.
- The public repo does not connect to a partner system.
- The prototype does not send outbound network traffic.
- Shadow evaluation is benchmark-only and does not change partner-facing decisions.
- Live use requires separate security, tenant isolation, data governance, and operating-model approval.

## Actors

- Utility product owner: owns pilot scope, success metrics, and readiness decision.
- Utility operations lead: reviews workflow behavior, timeout fallback, and restoration closure.
- Enterprise account lead: aligns product narrative and partner value.
- Partner NOC lead: reviews operator workflow, retry behavior, and action guidance.
- Governance reviewer: reviews data boundary, access expectations, retention, and de-identification.

## Pilot Surfaces

- Executive demo: `/demo/incidents`
- Operator console: `/demo/operator-console`
- Sandbox flow: `python scripts/run_partner_sandbox_flow.py`
- Scenario matrix: `python scripts/run_pilot_scenario_matrix.py`
- Readiness gate: `python scripts/generate_readiness_gate.py`
- Pilot evidence report: `python scripts/generate_pilot_report.py --format markdown`
- Partner pilot pack: `python scripts/generate_partner_pilot_pack.py --format markdown`

## Required Partner Inputs

Before moving from public demo to private sandbox planning, confirm:

- partner class and synthetic site scope for the pilot
- NOC review owner and utility operations review owner
- success metrics and minimum evidence threshold
- data minimization and retention expectations
- escalation labels and review cadence
- criteria that would stop the pilot before private data is used

## Operating Model

Use a simple RACI structure:

- Utility product owner approves pilot scope.
- Partner operations sponsor approves partner workflow fit.
- Utility operations lead validates outage decision flow.
- Partner NOC lead validates action labels and retry discussion.
- Governance reviewers approve data handling before operational data is introduced.
- Pilot steering group owns go/no-go decisions.

## Go Criteria

- Synthetic sandbox flow passes from a clean checkout.
- Readiness gate returns `ready_for_private_sandbox_discussion`.
- Scenario matrix has no failed synthetic cases.
- Shadow evaluation validates the pilot data contract.
- Pilot pack shows risks and production gaps clearly.

## No-Go Criteria

- Generated output exposes private auth material, network delivery targets, or operational topology.
- Duplicate handling, timeout fallback, or restoration closure evidence is missing.
- Reports imply production readiness.
- Governance owners are not assigned before any private data is used.
- Success metrics are not agreed before pilot evaluation begins.

## Handoff

If the pilot pack is accepted, the next engineering lane should be a private implementation plan for partner authorization, tenant isolation, managed storage, delivery worker behavior, live observability, and data governance controls.
