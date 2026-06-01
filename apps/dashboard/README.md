# Demo Surfaces

The current public-safe prototype exposes two lightweight FastAPI HTML surfaces:

- `/demo/incidents` with `/api/v1/demo/executive-summary` for the executive partner walkthrough
- `/demo/operator-console` with `/api/v1/operator/console-summary` for operator pilot workflow review

The executive page is designed to tell the product story in a short partner walkthrough:

- incident opened by an enterprise partner event
- immediate ETA and partner action returned
- field evidence revises ETA and confidence
- timeout failsafe prevents stalled decisions
- webhook outbox and sandbox delivery attempts show partner notification readiness
- restoration closure creates analytics and ML ground truth

The operator console is designed around live workflow questions:

- which active incidents need partner attention now
- which incidents are approaching or using timeout fallback
- which webhook delivery records still need retry or awareness
- what partner action should be taken for each active incident
- whether closed-loop data coverage is ready for evaluation

The current implementation intentionally stays inside the FastAPI service so the repo remains easy to clone and run. A separate frontend can be added later when the operator dashboard needs richer interactivity.

A production dashboard could be split into a separate frontend and add:

- partner NOC/SOC timeline view
- SLA and timeout indicators
- confidence and policy-explanation panels
- partner boundary and sandbox auth status
- webhook delivery state and retry queue
- audit event drill-down
- ETA accuracy and prolonged-outage performance views
