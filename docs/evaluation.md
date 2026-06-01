# Evaluation

This MVP keeps the first evaluation layer deliberately simple: rules are measured before adding heavier ML models.

## Rule Evaluation

Run the API and rule regression suite:

```bash
pytest -q
```

Run coverage:

```bash
pytest --cov=apps --cov-report=term-missing
```

## ETA Baseline

Train a reproducible baseline from synthetic closed incidents:

```bash
python scripts/train_eta_baseline.py
```

The current baseline predicts restoration duration from the mean duration by `scada_status`. It reports:

- `mae_hours`
- `underestimation_rate`
- trained group means

This is intentionally simple. Its job is to make the ML data loop inspectable before adding richer models.
