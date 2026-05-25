# Abstract Interval Analysis System — Debugging Task

## Overview

A static analysis system computes abstract interval approximations of program variables by interpreting structured execution traces over an interval domain. The system handles sequential assignments, conditional branches, and loops with widening for termination guarantees.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source, configuration, data, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **No external dependencies**: stdlib only

## Architecture

The system processes program traces through the following stages:

1. **Initialization** — Variable bounds are set from trace specifications.

2. **Sequential Transfer** — Arithmetic operations (add, sub, mul) are applied using interval arithmetic transfer functions.

3. **Branch Processing** — Conditional branches split execution into then/else paths. Each path is analyzed independently. At the merge point after the branch, the abstract state must soundly represent all values that could result from either path.

4. **Loop Analysis** — Loops are analyzed using Kleene iteration with widening. The loop body is repeatedly applied until a post-fixed point is reached. Widening accelerates convergence by extrapolating unstable bounds to infinity. Narrowing then refines the over-approximation.

5. **Reporting** — Final abstract values for all variables are written as structured JSON.

## Abstract Domain

The interval domain represents sets of integers as closed intervals `[lo, hi]`. Special elements:
- **Bottom** (⊥): the empty set — represents unreachable states
- **Top** (⊤): all integers — `[-∞, +∞]`

The domain forms a complete lattice ordered by subset inclusion.

## Soundness Requirement

The analysis must produce a **sound over-approximation**: the abstract interval for each variable must CONTAIN every concrete value that could occur during any actual execution of the trace. Under-approximation (missing possible values) is unsound and constitutes a correctness defect.

## Problem

The system runs without errors but produces intervals that are too narrow in traces involving conditional branches. Some variables that should have wide ranges are being computed with restricted bounds, and some variables that should be non-empty intervals are being reported as bottom (empty). The analysis appears to under-approximate rather than over-approximate at certain program points.

## Expected Correct Output

The analysis should produce sound over-approximations for all traces:
- **trace_alpha**: After a branch where x is increased on one path and decreased on the other, x must span the full range of both paths
- **trace_beta**: Loop variables must widen to reflect unbounded iteration
- **trace_gamma**: A loop containing a branch that both increments and decrements a variable must produce a wide (unbounded) interval
- **trace_delta**: Nested branches must propagate ranges from all sub-paths

## Output Schema

### `/app/runtime/output/summary.json`

| Field | Type | Description |
|-------|------|-------------|
| `total_traces` | int | Number of traces analyzed |
| `trace_ids` | array | List of trace identifiers |
| `variables_per_trace` | object | Map of trace_id to list of variable names |

### `/app/runtime/output/analysis_results.json`

Top-level object keyed by trace_id. Each entry contains:

| Field | Type | Description |
|-------|------|-------------|
| `trace_id` | string | Trace identifier |
| `description` | string | Human-readable trace description |
| `variables` | object | Map of variable name to abstract interval |

Each variable entry in `variables`:

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Either "interval" or "bottom" |
| `lo` | int or null | Lower bound (null = -∞), absent if bottom |
| `hi` | int or null | Upper bound (null = +∞), absent if bottom |

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/run_analysis.py` | Entry point — loads traces, runs analyzer, writes output |
| `/app/runtime/domain.py` | Interval domain — lattice operations, transfer functions, merge |
| `/app/runtime/analyzer.py` | Trace analyzer — processes instructions, branches, loops |
| `/app/runtime/config.ini` | Analysis parameters (widening delay, max iterations) |
| `/app/runtime/data/trace_alpha.json` | Simple branch merge trace |
| `/app/runtime/data/trace_beta.json` | Loop with widening trace |
| `/app/runtime/data/trace_gamma.json` | Branch inside loop trace |
| `/app/runtime/data/trace_delta.json` | Nested branches trace |

## Your Task

Identify and fix the defect in the runtime source files so that the analysis produces sound over-approximations. The configuration and data files are correct. Focus on the abstract domain operations and how they are used at control flow merge points.
