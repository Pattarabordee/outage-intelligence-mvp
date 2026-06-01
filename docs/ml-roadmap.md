# ML Data Product Roadmap

The product starts with explainable rules because enterprise outage decisions need transparent reasoning before model complexity. The long-term value comes from closed-loop ground truth and partner-level evaluation.

## Supervised Learning Targets

- Actual restoration duration
- ETA error
- Prolonged-outage probability
- Partner action quality
- Timeout fallback frequency

## Dataset Export

Closed incidents can be exported as JSONL for offline analysis:

```bash
python scripts/export_closed_dataset.py --output data/runtime/closed-incidents.jsonl
```

Each row includes:

- `prediction_time`
- `actual_restoration_duration_hours`
- `initial_eta_hours`
- `eta_error_hours`
- `rule_version`
- `feature_snapshot`

## Baseline Model

The first baseline is intentionally simple and reproducible:

```bash
python scripts/train_eta_baseline.py
```

It predicts restoration duration from historical mean duration grouped by `scada_status`, then reports MAE and underestimation rate. This provides a measurable floor before introducing richer supervised-learning models.

## Candidate Features

Structured:

- site class
- partner class
- region or weather context
- network segment class
- outage start time
- initial SCADA condition
- number of field signals
- time since incident open
- timeout applied flag

Text-derived:

- cause keywords
- severity phrases
- repair-action phrases
- restoration confidence phrases

## Future Models

- ETA regression baseline
- Prolonged-outage classifier
- Survival analysis for restoration time
- Partner-level calibration and reliability reports
- Dispatch decision policy optimization

Any future model should be evaluated against the current rules-first baseline before being used for operational recommendations.
