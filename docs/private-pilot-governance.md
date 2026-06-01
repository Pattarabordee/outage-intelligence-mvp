# Private Pilot Governance

This governance note defines the boundary between the public-safe prototype, a private sandbox discussion, and a future production implementation.

## Public-Safe Boundary

The repository may be shared publicly because it uses:

- synthetic partner, site, incident, and metric examples
- local service simulation for partner flow
- local outbox records instead of outbound network dispatch
- deterministic rules and benchmark-only ML evaluation
- public-safe reports that exclude private auth material, network delivery targets, raw operational text, and production topology

## Data Handling

For a private sandbox, treat data handling as a gate, not a detail to fill in later.

- Define which outage event fields are required and which are excluded.
- Minimize partner identifiers to the smallest usable scope.
- Keep field notes summarized into reason codes where possible.
- Separate operational evidence from reporting artifacts.
- Review any export format before it is shared outside the pilot working group.

## Retention And De-Identification

Before using operational data, agree on:

- retention duration for incident, signal, delivery, and restoration records
- de-identification rules for site, partner, field, and operator references
- export review process for evaluation datasets
- deletion or archival process after the pilot
- ownership of benchmark and shadow-evaluation outputs

## Access Control Expectations

The public prototype includes a lightweight sandbox boundary for local discussion. A private pilot needs a stronger design:

- partner-scoped authorization policy
- managed partner registry and site authorization source of truth
- replay-window and rate-limit policy
- audit review for operator and service actions
- separate administrative and partner-facing surfaces

## Audit And Evidence

The pilot evidence pack should be used to review:

- incident lifecycle evidence
- ETA revision rationale
- timeout fallback coverage
- restoration ground-truth coverage
- local retry behavior
- scenario matrix coverage
- shadow evaluation readiness
- public-safe scan status

## Known Production Gaps

The prototype should not be treated as live-ready until these are closed:

- production-grade authorization
- managed database and migration plan
- managed outbound delivery worker
- receiver-side verification in the private environment
- live observability and alert routing
- approved retention, de-identification, and governance process
- operational runbooks with named owners and escalation paths
