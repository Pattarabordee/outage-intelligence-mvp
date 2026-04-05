# Business Case

This public-safe MVP demonstrates how outage intelligence can reduce uncertainty for power-sensitive operations without requiring a full machine-learning platform on day one.

## Core value proposition

An enterprise client that depends on continuous power typically faces two expensive mistakes:

1. Dispatch backup resources too early and absorb unnecessary operating cost.
2. Dispatch too late and absorb avoidable service disruption.

The MVP reduces both mistakes by splitting the decision flow into two stages:

- an immediate recommendation when the outage event is opened
- a revised ETA when field evidence adds clarity

## Why this works as an MVP

- It is useful before any model training exists.
- It keeps decision logic transparent through rule-based reasoning.
- It creates the event history needed for later analytics and ML.
- It is easy to explain to engineering, operations, and product stakeholders.

## Why it works well in interviews

This repository shows more than CRUD APIs. It demonstrates:

- workflow design for real operational decisions
- explainable ETA revision logic
- timeout-based resilience for incomplete information
- closed-loop data capture for future model training
- disciplined public-safe documentation and demo packaging
