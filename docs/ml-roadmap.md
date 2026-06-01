# ML Roadmap

The MVP deliberately starts with rules because they are fast to build and easy to explain. The long-term value comes from the data exhaust it captures.

## Supervised learning targets

- actual restoration time
- ETA error
- dispatch recommendation quality
- probability of prolonged outage

## Dataset export

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

## Candidate features

Structured:
- site class
- region / weather context
- network segment class
- outage start time
- initial SCADA condition
- number of field signals
- time since incident open

Text-derived:
- cause keywords
- severity phrases
- repair-action phrases
- restoration confidence phrases

## Future models

- ETA regression
- survival analysis for restoration time
- severity classification
- dispatch decision policy optimization
