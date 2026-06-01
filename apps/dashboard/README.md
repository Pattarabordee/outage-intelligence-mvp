# Executive Demo Surface

The current public-safe prototype exposes an executive partner demo at `/demo/incidents` and a sanitized JSON feed at `/api/v1/demo/executive-summary`.

The page is designed to tell the product story in a short partner walkthrough:

- incident opened by an enterprise partner event
- immediate ETA and partner action returned
- field evidence revises ETA and confidence
- timeout failsafe prevents stalled decisions
- webhook outbox and sandbox delivery attempts show partner notification readiness
- restoration closure creates analytics and ML ground truth

The current implementation intentionally stays inside the FastAPI service so the repo remains easy to clone and run. A separate frontend can be added later when the operator dashboard needs richer interactivity.

A production dashboard could be split into a separate frontend and add:

- partner NOC/SOC timeline view
- SLA and timeout indicators
- confidence and policy-explanation panels
- partner boundary and sandbox auth status
- webhook delivery state and retry queue
- audit event drill-down
- ETA accuracy and prolonged-outage performance views
