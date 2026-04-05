# Security and Governance Notes

This repository is public-safe by design.

## Excluded from the public repo

- real client names and identifiers
- real outage locations
- real field communication transcripts
- real GIS topology
- production credentials or network details
- real commercial pricing terms

## Governance principles

- minimize sensitive fields at ingestion
- separate operational logs from analytics extracts
- hash or tokenize client-side identifiers when possible
- keep explainable rules for high-impact operational decisions
- audit every ETA revision and incident closure
