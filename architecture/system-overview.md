# System Overview

This architecture models a public-safe enterprise outage intelligence product for utility-to-partner coordination.

```mermaid
flowchart LR
    A[Utility Operations] --> B[Enterprise Outage API]
    C[Enterprise Partner System] --> B
    B --> D[Decision Policy Engine]
    D --> E[ETA + Partner Action]

    F[Field Signals] --> G[Text Signal Rules]
    G --> D
    D --> H[(Incident + Audit Store)]

    I[Timeout Failsafe] --> D
    J[Restoration Ground Truth] --> H
    H --> K[ML Dataset Export]
    H --> L[Executive Demo Timeline]
```

## Product Responsibilities

- Utility operations provide outage state, field evidence, and restoration closure.
- Enterprise partner systems receive ETA, confidence, policy explanation, and action guidance.
- The API keeps partner writes retry-safe through source IDs and idempotency keys.
- The audit store preserves why decisions changed.
- Dataset export converts closed incidents into ML-ready training and evaluation rows.
