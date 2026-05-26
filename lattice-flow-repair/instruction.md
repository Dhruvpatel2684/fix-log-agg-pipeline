# Lattice Flow Anomaly Correlation Engine

## Overview

The Lattice Flow system is a distributed monitoring anomaly correlator. It processes anomaly events detected across a microservice dependency graph and determines which anomalies are **causally related** (one failure propagated through service dependencies to cause another) versus **coincidental** (temporally proximate but not causally linked).

The system ingests trace datasets containing:
- A directed service dependency graph with propagation delay annotations on each edge
- A set of anomaly events detected at various services with timestamps
- Ground truth labels for evaluation

## Architecture

The system consists of the following modules:

| Module | Path | Responsibility |
|--------|------|----------------|
| Graph | `/app/runtime/graph.py` | Service dependency graph representation with reachability, shortest path, and delay computation |
| Events | `/app/runtime/events.py` | Anomaly event parsing, timeline management, and ground truth label storage |
| Correlator | `/app/runtime/correlator.py` | Core correlation engine that classifies event pairs as causal or independent |
| Aggregator | `/app/runtime/aggregator.py` | Aggregates correlation results into reports with causal chain detection |
| Metrics | `/app/runtime/metrics.py` | Computes precision, recall, F1, and confusion matrices against ground truth |
| Runner | `/app/runtime/run_analysis.py` | Entry point that orchestrates the full analysis across trace datasets |

## Data Format

Trace files are located at `/app/runtime/data/trace_*.json` with this schema:

| Field | Type | Description |
|-------|------|-------------|
| `graph.services` | `string[]` | List of service identifiers |
| `graph.edges` | `object[]` | Directed edges with `source`, `target`, `propagation_delay_ms` |
| `events` | `object[]` | Anomaly events with `event_id`, `service_id`, `timestamp_ms`, `severity`, `metric_name`, `metric_value`, `baseline_value`, `deviation_sigma` |
| `ground_truth` | `object[]` | Labels with `event_a`, `event_b`, `relationship` (causal/independent) |

## Correlation Output Schema

| Field | Type | Description |
|-------|------|-------------|
| `event_a_id` | `string` | First event identifier |
| `event_b_id` | `string` | Second event identifier |
| `classification` | `string` | One of: `causal`, `independent` |
| `confidence` | `float` | Confidence score [0, 1] |
| `path` | `string[]` | Service path if causal |
| `propagation_delay_ms` | `float` | Estimated propagation delay |

## Evaluation Metrics Schema

| Metric | Description |
|--------|-------------|
| `precision` | Fraction of predicted causal pairs that are truly causal |
| `recall` | Fraction of truly causal pairs that are correctly predicted |
| `f1_score` | Harmonic mean of precision and recall |
| `true_positives` | Correctly identified causal pairs |
| `false_positives` | Independent pairs incorrectly labeled causal |
| `true_negatives` | Correctly identified independent pairs |
| `false_negatives` | Causal pairs incorrectly labeled independent |

## Known Issue

The correlation engine is producing an excessive number of false positives — it classifies many event pairs as causally related when they should be independent. This results in low precision scores across all trace datasets. The recall is acceptable but precision degrades significantly when events from connected services occur in rapid succession.

## Running the Analysis

```bash
cd /app
python -m runtime.run_analysis
```

## Global system-wide tooling: uv and pytest are available.
