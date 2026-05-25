# Temporal Constraint Propagation Scheduler

## System Overview

This system determines whether proposed task schedules are satisfiable under temporal ordering constraints. Each task has a feasible time window (earliest and latest start times) and a fixed duration. Ordering constraints specify that one task must complete before another begins.

The analysis proceeds in three stages:

1. **Constraint Propagation** — Iteratively tightens the feasible windows for each task based on the ordering relationships. If task A must complete before task B begins, then A's completion time bounds B's start, and B's start bounds A's completion.

2. **Feasibility Check** — After propagation, verifies that every task still has a non-empty feasible window (earliest start does not exceed latest start).

3. **Satisfiability Assessment** — Checks whether the propagated bounds admit an assignment where all ordering constraints are respected simultaneously.

## Environment

- All source code is located at `/app/runtime/`
- Scenario data files are in `/app/runtime/data/`
- Configuration is in `/app/runtime/config.ini`
- Output is written to `/app/runtime/output/`
- Entry point: `python -m runtime.run_analysis`

## Task Representation

Each task has:
- `earliest_start` — the earliest time the task can begin
- `latest_start` — the latest time the task can begin
- `duration` — fixed execution time

From these, derived bounds are computed:
- `earliest_end = earliest_start + duration`
- `latest_end = latest_start + duration`

Tasks occupy the half-open time interval `[start, start + duration)`.

## Constraint Semantics

A constraint `{"type": "before", "from": "A", "to": "B"}` means task A must complete before task B begins. The propagator tightens bounds to reflect these relationships, and the checker verifies that the final bounds admit valid orderings.

## Scenarios

Four scheduling scenarios are evaluated:
- **alpha** — Linear task chain with tight intervals
- **beta** — Parallel tasks feeding into a shared successor
- **gamma** — Cascading phases with indirect dependency propagation
- **delta** — Transitive chain with impossible time constraints

## Expected Behavior

After correct analysis, satisfiable scenarios should report `satisfiable: true` and unsatisfiable scenarios should report `satisfiable: false`. The system propagates constraints to tighten feasible windows and then assesses whether valid assignments exist.

## Global Tooling

Global system-wide tooling: `uv` and `pytest` are available for testing and dependency management.
