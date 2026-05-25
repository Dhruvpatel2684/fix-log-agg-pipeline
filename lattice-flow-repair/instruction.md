# Lattice-Based Information Flow Analyzer — Debugging Task

## Overview

A security analysis system processes information flow events from multiple organizational departments, classifying flows against a lattice-based security model. The system loads event streams, applies the lattice ordering to determine combined classifications, detects violations based on configurable thresholds, computes flow volumes across time windows, and produces structured JSON reports.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source, configuration, data, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **No external dependencies**: stdlib only

## Architecture

The system consists of four processing stages:

1. **Loading & Merging** — Department event streams (`/app/runtime/data/*_flows.json`) are loaded and merged into a single chronological sequence. Events are sorted by timestamp, then by source department identifier, then by local sequence number for deterministic ordering when timestamps collide.

2. **Filtering & Classification** — Events are filtered to only those from monitored departments (configured in `/app/runtime/config.ini` under `[lattice]`). Each flow's security classification is computed using lattice operations. In a totally-ordered security lattice, the combined classification of two labels is their **least upper bound (join/supremum)** — the higher of the two levels — ensuring merged information receives adequate protection.

3. **Violation Detection** — Flows are evaluated against the strict analysis threshold (`/app/runtime/config.ini` section `[analysis.strict]`). Any flow crossing two or more lattice levels is flagged as a violation. The violation count, combined labels, and distances are recorded.

4. **Volume Aggregation** — Entity flow volumes are tracked across fixed time windows. Volume counters represent point-in-time snapshots: when an entity appears in a new window, that window's value supersedes (replaces) any prior window's value. The final reported volume for each entity is from its most recent window appearance.

## Problem

The system runs without errors but produces incorrect output. Reports show fewer monitored events than expected, no violations are being flagged despite clearly sensitive cross-boundary flows, flow volumes appear inflated for entities that span multiple time windows, and combined classification labels seem inverted from what the security model requires.

## Expected Correct Output

When functioning correctly, the system should:

- Monitor all 54 events from the four configured departments (engineering, research, operations, compliance)
- Detect 27 violations at the strict threshold (flow distance ≥ 2)
- Report the combined classification as the **upper** label for each violating flow
- Compute entity volumes using last-write-wins window semantics
- Include `restricted` in the flow matrix (compliance department source label)

## Output Schema

### `/app/runtime/output/summary.json`

| Field | Type | Description |
|-------|------|-------------|
| `total_events_loaded` | int | Total events loaded from all department sources |
| `monitored_events` | int | Events from monitored departments after filtering |
| `total_violations` | int | Number of detected security violations |
| `entities_with_volume` | int | Count of unique entities with computed volumes |
| `flow_matrix_sources` | int | Number of distinct source labels in flow matrix |

### `/app/runtime/output/violations.json`

| Field | Type | Description |
|-------|------|-------------|
| `violation_count` | int | Total number of violations detected |
| `violations` | array | List of violation records |
| `violations[].event_id` | string | Unique event identifier |
| `violations[].source_id` | string | Department that generated the event |
| `violations[].entity` | string | Data entity involved in the flow |
| `violations[].from_label` | string | Source security classification |
| `violations[].to_label` | string | Destination security classification |
| `violations[].combined_label` | string | Lattice join of from and to labels |
| `violations[].distance` | int | Lattice distance between labels |
| `violations[].timestamp` | string | ISO 8601 timestamp of the event |

### `/app/runtime/output/flow_matrix.json`

| Field | Type | Description |
|-------|------|-------------|
| `<from_label>` | object | Mapping from source label to destination counts |
| `<from_label>.<to_label>` | int | Count of flows from source to destination label |

### `/app/runtime/output/volumes.json`

| Field | Type | Description |
|-------|------|-------------|
| `entity_volumes` | object | Mapping of entity names to their final flow volume |
| `entity_volumes.<entity_name>` | int | Final computed volume for the entity |

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/run_analysis.py` | Entry point orchestrating all stages |
| `/app/runtime/lattice.py` | Security lattice operations (ordering, combined labels) |
| `/app/runtime/analyzer.py` | Flow analysis engine (filtering, violations, volumes) |
| `/app/runtime/loader.py` | Event loading and merge-sorting from department files |
| `/app/runtime/reporter.py` | JSON report generation |
| `/app/runtime/config.ini` | Lattice levels, monitored departments, analysis parameters |
| `/app/runtime/data/engineering_flows.json` | Engineering department event stream |
| `/app/runtime/data/research_flows.json` | Research department event stream |
| `/app/runtime/data/compliance_flows.json` | Compliance department event stream |

## Your Task

Identify and fix defects in the runtime source files so that the analysis produces correct output. The configuration file and data files are correct and should not be modified. Focus on the Python source modules where the processing logic resides.
