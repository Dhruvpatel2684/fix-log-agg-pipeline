# Product Lattice Information Flow Analyzer — Debugging Task

## Overview

A security analysis system evaluates information flows across a two-dimensional classification lattice. Each flow event carries both a confidentiality label and an integrity label, forming a product lattice where the partial order, distance metric, and join operation must account for both dimensions simultaneously. The system loads events from multiple organizational sources, deduplicates them, detects violations against the product lattice ordering, and generates structured reports.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source, configuration, data, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **No external dependencies**: stdlib only

## Architecture

The system processes information flow events through four stages:

1. **Loading & Deduplication** — Flow event streams from `/app/runtime/data/*_flows.json` are loaded and merged into a chronological sequence (sorted by timestamp, then source identifier, then local sequence number). Events are then deduplicated: events referencing the same entity from the same source stream within a time window are consolidated. Events from different sources that happen to reference the same entity are independent observations and must be preserved.

2. **Dominance Classification** — Each flow is evaluated against the product lattice ordering. The product lattice L = C × I uses **componentwise ordering**: element (c1, i1) is dominated by (c2, i2) if and only if c1 ≤ c2 AND i1 ≤ i2 (with at least one strict inequality). This is a partial order — elements where one dimension increases while the other decreases are **incomparable** and must not be classified as upward flows.

3. **Violation Detection** — Flows classified as upward (destination dominates source) are checked against the configured distance threshold. The distance in a product lattice is the **L-infinity (Chebyshev) metric**: the maximum of the individual dimensional displacements. A flow crossing 3 levels in confidentiality but 1 in integrity has distance 3. Only flows exceeding the threshold are violations.

4. **Join Computation & Reporting** — For each violation, the combined classification is computed as the **join (least upper bound)** in the product lattice. The join of (c1, i1) and (c2, i2) is (max(c1, c2), max(i1, i2)) — the componentwise maximum. Reports are generated including violation details, flow matrices, and per-source volumes.

## Problem

The system runs without errors but produces incorrect results. The violation count is substantially higher than expected, some flows between incomparable classification labels are being incorrectly flagged, combined classification labels appear to be computed at a lower level than the correct upper bound, per-source volume totals are inconsistent with the input data, and some legitimate events from independent sources appear to be missing from the analysis.

## Expected Correct Output

When functioning correctly, the system should:

- Load all 54 events and retain all 54 after deduplication (no true duplicates exist in the data)
- Detect exactly 9 violations (flows where both dimensions increase and the Chebyshev distance exceeds 2)
- Exclude incomparable flows (where one dimension increases but the other decreases) from violations
- Report combined classifications as the componentwise maximum of the from/to labels
- Report research source volume as 328 (sum of all 18 research event volumes)

## Output Schema

### `/app/runtime/output/summary.json`

| Field | Type | Description |
|-------|------|-------------|
| `total_events_loaded` | int | Total events loaded from all source files |
| `events_after_dedup` | int | Events remaining after deduplication |
| `total_violations` | int | Number of detected security violations |
| `source_volumes` | object | Mapping of source_id to total volume |
| `flow_matrix_size` | int | Number of distinct source confidentiality labels |

### `/app/runtime/output/violations.json`

| Field | Type | Description |
|-------|------|-------------|
| `violation_count` | int | Total violations detected |
| `violations` | array | List of violation records |
| `violations[].event_id` | string | Unique event identifier |
| `violations[].source_id` | string | Source stream that generated the event |
| `violations[].entity` | string | Data entity involved in the flow |
| `violations[].from_conf` | string | Source confidentiality label |
| `violations[].from_integ` | string | Source integrity label |
| `violations[].to_conf` | string | Destination confidentiality label |
| `violations[].to_integ` | string | Destination integrity label |
| `violations[].combined_conf` | string | Join confidentiality (componentwise max) |
| `violations[].combined_integ` | string | Join integrity (componentwise max) |
| `violations[].distance` | int | Chebyshev distance between labels |
| `violations[].timestamp` | string | ISO 8601 timestamp |

### `/app/runtime/output/flow_matrix.json`

| Field | Type | Description |
|-------|------|-------------|
| `<from_conf>` | object | Mapping from source conf label to destination counts |
| `<from_conf>.<to_conf>` | int | Count of flows between confidentiality levels |

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/run_analysis.py` | Entry point orchestrating all stages |
| `/app/runtime/lattice.py` | Product lattice operations (dominance, join, distance) |
| `/app/runtime/analyzer.py` | Violation detection and flow matrix computation |
| `/app/runtime/loader.py` | Event loading, sorting, and deduplication |
| `/app/runtime/reporter.py` | JSON report generation |
| `/app/runtime/config.ini` | Lattice dimensions, thresholds, dedup window |
| `/app/runtime/data/engineering_flows.json` | Engineering source event stream |
| `/app/runtime/data/research_flows.json` | Research source event stream |
| `/app/runtime/data/compliance_flows.json` | Compliance source event stream |

## Your Task

Identify and fix defects in the runtime source files so that the analysis produces correct output. The configuration file and data files are correct and should not be modified. Focus on the Python source modules where the lattice operations and deduplication logic reside.
