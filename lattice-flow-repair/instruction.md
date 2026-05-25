# Temporal Constraint Propagation Scheduler — Debugging Task

## Overview

A temporal analysis system determines whether proposed task schedules are satisfiable under ordering constraints. Each task has a feasible time window and a fixed duration. Ordering constraints specify that one task must complete before another begins. The system propagates constraints, checks feasibility, and reports satisfiability.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source, configuration, data, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **No external dependencies**: stdlib only

## Processing Stages

1. **Constraint Propagation** — Iteratively tightens the feasible windows for each task based on ordering relationships. If task A must complete before task B begins, then A's completion time bounds B's start, and B's start bounds A's completion. Propagation runs for multiple passes until bounds converge.

2. **Feasibility Check** — After propagation, verifies that every task still has a non-empty feasible window (earliest start does not exceed latest start). Tasks with empty windows are reported as infeasible.

3. **Satisfiability Assessment** — Checks whether the propagated bounds admit an assignment where all ordering constraints are respected simultaneously. Reports which constraints are violated, if any.

## Task Representation

Each task has:
- `earliest_start` — the earliest time the task can begin
- `latest_start` — the latest time the task can begin
- `duration` — fixed execution time

Derived bounds:
- `earliest_end = earliest_start + duration`
- `latest_end = latest_start + duration`

Tasks occupy the half-open time interval `[start, start + duration)`.

## Constraint Semantics

A constraint `{"type": "before", "from": "A", "to": "B"}` means task A must complete before task B begins. For half-open intervals, A finishing at exactly time T and B starting at time T means they do not overlap (A occupies `[..., T)` and B occupies `[T, ...)`).

## Scenarios

Four scheduling scenarios are evaluated (configured in `/app/runtime/config.ini`):
- **alpha** — Linear task chain with tight intervals
- **beta** — Parallel tasks feeding into a shared successor
- **gamma** — Cascading phases with indirect dependency propagation
- **delta** — Transitive chain with impossible time constraints

## Problem

The system runs without errors but produces incorrect satisfiability results. Scenarios that should be satisfiable are reported as unsatisfiable. Propagated bounds appear over-tightened, and constraint checking seems overly strict at interval boundaries.

## Expected Correct Output

When functioning correctly:
- **alpha**: `satisfiable = true` (all constraints met with zero separation at boundary)
- **beta**: `satisfiable = true` (parallel predecessors complete before successor)
- **gamma**: `satisfiable = true` (cascading constraints fully propagated)
- **delta**: `satisfiable = false` (genuinely impossible — task durations exceed available time)

## Output Schema

The system produces two output files in `/app/runtime/output/`:

### `/app/runtime/output/summary.json`

| Field | Type | Description |
|-------|------|-------------|
| `total_scenarios` | int | Number of scenarios processed |
| `satisfiable_count` | int | Scenarios with satisfiable=true |
| `unsatisfiable_count` | int | Scenarios with satisfiable=false |
| `scenario_results` | object | Map of scenario_id to boolean satisfiability |

### `/app/runtime/output/schedule_analysis.json`

Top-level object keyed by scenario_id. Each scenario entry contains:

| Field | Type | Description |
|-------|------|-------------|
| `scenario_id` | string | Identifier for the scenario |
| `satisfiable` | boolean | Whether the schedule is satisfiable |
| `feasible_windows` | boolean | Whether all task windows are non-empty after propagation |
| `infeasible_tasks` | array | List of task names with empty windows |
| `constraints_satisfied` | boolean | Whether all ordering constraints are met |
| `violated_constraints` | array | List of constraint strings that are violated |
| `constraint_details` | array | Per-constraint satisfaction details |
| `propagated_bounds` | object | Map of task name to propagated timing bounds |

Each entry in `propagated_bounds` contains:

| Field | Type | Description |
|-------|------|-------------|
| `earliest_start` | int | Tightened earliest start time |
| `latest_start` | int | Tightened latest start time |
| `duration` | int | Fixed task duration |
| `earliest_end` | int | Tightened earliest end time |
| `latest_end` | int | Tightened latest end time |

Each entry in `constraint_details` contains:

| Field | Type | Description |
|-------|------|-------------|
| `constraint` | string | Human-readable constraint description |
| `pred_earliest_end` | int | Predecessor's earliest end after propagation |
| `succ_latest_start` | int | Successor's latest start after propagation |
| `separation` | int | Temporal gap between predecessor end and successor start |
| `satisfied` | boolean | Whether this individual constraint is met |

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/run_analysis.py` | Entry point orchestrating all stages |
| `/app/runtime/intervals.py` | Temporal interval operations (overlap, separation, bounds) |
| `/app/runtime/propagator.py` | Constraint propagation engine |
| `/app/runtime/checker.py` | Satisfiability assessment |
| `/app/runtime/config.ini` | Scheduler parameters and active scenarios |
| `/app/runtime/data/alpha_scenario.json` | Alpha scenario definition |
| `/app/runtime/data/beta_scenario.json` | Beta scenario definition |
| `/app/runtime/data/gamma_scenario.json` | Gamma scenario definition |
| `/app/runtime/data/delta_scenario.json` | Delta scenario definition |

## Your Task

Identify and fix defects in the runtime source files and configuration so that the analysis produces correct satisfiability results. The scenario data files are correct and should not be modified. Focus on the interval operations, propagation logic, and configuration parameters.
