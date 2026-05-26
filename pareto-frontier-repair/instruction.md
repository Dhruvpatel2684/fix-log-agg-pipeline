# Pareto Frontier Analyzer — Incident Report

## Context

We have a multi-objective optimization analyzer that computes Pareto frontiers from solution evaluations across multiple evaluators. It processes objective scores, normalizes them, determines dominance relationships, and produces a frontier ranking report. This has been running in production for months, but after a recent refactor the outputs started drifting.

## Symptoms

Our reference implementation (verified against NSGA-II paper results) produces a known-good frontier decomposition for the same objective data. When we compare:

1. **Non-dominated pairs are severely undercounted** — We expect hundreds of non-dominated pairs (solutions on the same trade-off surface), but the system reports almost none. It's classifying nearly everything as dominated.

2. **Normalization appears inconsistent** — AGGREGATE solutions that should produce identical normalized values to their RAW counterparts are showing different numbers. Early solutions seem to be normalized against incomplete bounds.

3. **The frontier ranking doesn't match NSGA-II output** — The ranking appears to be a simple sort by objective values, which... isn't how Pareto fronts work. Lexicographic ordering ≠ non-dominated sorting.

4. **Fingerprint drifts between evaluator configurations** — The frontier fingerprint (SHA-256 of the dominance graph structure) doesn't match the reference. This blocks our CI because we use the fingerprint for regression detection.

## System Architecture

The processing flow is:

```
objectives.txt → objective_parser.py → dominance_engine.py → frontier_analyzer.py → report_writer.py
                                                                                        ↓
                                                                    pareto_state.jsonl + pareto_report.json
```

- `pareto_engine.py` — Orchestrator. Reads objectives, runs the flow, writes output. This file is fine.
- `objective_parser.py` — Parses the pipe-delimited objectives format. This file is fine.
- `dominance_engine.py` — Normalizes raw objectives to [0,1] using min-max scaling.
- `frontier_analyzer.py` — Classifies all solution pairs as dominance or non-dominated. Computes frontier ranking.
- `report_writer.py` — Writes the JSONL state file and JSON report with fingerprint.

## Input Format

The objectives file (`objectives.txt`) uses pipe-delimited fields:

```
SOLUTION_ID|EVALUATOR|OBJ_TYPE|VALUES
```

- SOLUTION_ID: unique identifier
- EVALUATOR: which evaluator produced the scores (eval_alpha, eval_beta, eval_gamma)
- OBJ_TYPE: RAW (needs normalization), NORMALIZED (already [0,1]), AGGREGATE (combined scores)
- VALUES: comma-separated objective scores (4 objectives: latency, throughput, cost, reliability)

## Output Schema

### `/app/runtime/pareto_state.jsonl`

One JSON object per line, one per solution:
```json
{"solution_index": 0, "solution_id": "S01", "evaluator": "eval_alpha", "obj_type": "RAW", "normalized_objectives": [0.667, 0.462, 0.600, 0.444]}
```

### `/app/runtime/pareto_report.json`

```json
{
  "evaluator_ids": ["eval_alpha", "eval_beta", "eval_gamma"],
  "total_solutions": 27,
  "solutions_per_evaluator": {"eval_alpha": 10, "eval_beta": 9, "eval_gamma": 8},
  "dominance_count": <int>,
  "nondominated_count": <int>,
  "frontier_ranking": [<solution indices in frontier order>],
  "asymmetry_holds": <bool>,
  "frontier_fingerprint": "<16-char hex string>"
}
```

## Environment

- Python 3.11 available system-wide
- Global system-wide tooling: `uv` and `pytest` are available
- No external dependencies needed (stdlib only)
- Output files go in `/app/runtime/`
- Run with: `python3 /app/runtime/pareto_engine.py`

## What We Need

Find and fix the bugs causing the symptoms above. The objectives file and parser are correct — the issues are in how objectives are normalized, how dominance relationships are determined, and how the report is generated.

Don't add dependencies. Don't change the input format or output schema. Just make the numbers right.
