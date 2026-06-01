# Pilot Risk Register

This risk register supports private sandbox discussion. It does not certify production readiness.

| ID | Area | Risk | Impact | Mitigation | Current Status | Production Gate |
| --- | --- | --- | --- | --- | --- | --- |
| RISK-001 | Security | Sandbox authentication is suitable for discussion but not enough for live partner access. | A live pilot would require stronger authorization and operational controls. | Keep this repo local and public-safe; implement production-grade auth in a private service. | Known gap | Approved partner authorization policy |
| RISK-002 | Tenant Boundary | SQLite and synthetic site prefixes are not a production tenant isolation model. | Private pilots need enforced partner-level boundaries and audit review. | Use managed storage, migration policy, and partner-scoped access checks before live use. | Known gap | Managed database with tenant policy |
| RISK-003 | Delivery | Webhook behavior is modeled through a local outbox only. | Delivery reliability cannot be certified until a private delivery worker is tested. | Treat retry evidence as sandbox proof; add private receiver verification before live pilot. | Ready for discussion | Managed delivery worker and receiver verification |
| RISK-004 | Evaluation | ML and shadow evaluation metrics are based on synthetic rows. | Metric direction is useful for discussion but not a production performance claim. | Run shadow evaluation on governed pilot data before changing partner-facing policy. | Ready for discussion | Approved shadow evaluation on governed data |
| RISK-005 | Operations | Runbooks are pilot discussion artifacts, not live incident procedures. | Operational ownership and escalation paths remain undefined for live use. | Assign utility and partner owners during private pilot planning. | Needs private pilot input | Approved live operating model |

## Review Cadence

Review this register at three points:

- before the first private sandbox walkthrough
- after scenario matrix and pilot report review
- before any operational data is introduced

## Decision Rule

Proceed only when the pilot steering group accepts every known gap as either safe for sandbox discussion or blocked until a private implementation exists.
