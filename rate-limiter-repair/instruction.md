# Sliding Window Rate Limiter — Incident Report

## Context

We have a distributed rate-limiting system that processes API request logs from multiple services, applies sliding window + token bucket rate limiting, classifies request pairs as conflicting or independent, and produces a scheduling report. This has been running in production for months, but after a recent refactor the outputs started drifting.

## Symptoms

Our reference implementation (verified against the token bucket RFC specification) produces a known-good scheduling decomposition for the same request data. When we compare:

1. **Independent pairs are severely undercounted** — We expect hundreds of independent pairs (requests with incomparable budget states), but the system reports almost none. It's classifying nearly everything as conflicting.

2. **Token budgets appear inconsistent** — REFILL events that should replenish tokens are showing stale values. Services that receive upstream state are not reflecting the expected post-refill budget — the receiver's own component should exceed the sender's value but instead they match exactly.

3. **The scheduling order doesn't match priority-based output** — The scheduling appears to be a simple sort by arrival timestamp, which... isn't how priority scheduling works. Timestamp ordering ≠ budget-priority scheduling.

4. **Fingerprint drifts between service configurations** — The throttle fingerprint (SHA-256 of the scheduling graph structure) doesn't match the reference. This blocks our CI because we use the fingerprint for regression detection.

## System Architecture

The processing flow is:

```
request_log.txt → request_parser.py → token_engine.py → throttle_analyzer.py → report_writer.py
                                                                                     ↓
                                                              throttle_state.jsonl + throttle_report.json
```

- `rate_engine.py` — Orchestrator. Reads requests, runs the flow, writes output. This file is fine.
- `request_parser.py` — Parses the pipe-delimited request format. This file is fine.
- `token_engine.py` — Maintains token buckets per service with sliding window semantics.
- `throttle_analyzer.py` — Classifies all request pairs as conflicting or independent. Computes scheduling order.
- `report_writer.py` — Writes the JSONL state file and JSON report with fingerprint.

## Input Format

The request log (`request_log.txt`) uses pipe-delimited fields:

```
TIMESTAMP|SERVICE|REQUEST_TYPE|PAYLOAD
```

- TIMESTAMP: milliseconds (monotonic per service)
- SERVICE: which service produced the request (svc_alpha, svc_beta, svc_gamma, svc_delta, svc_epsilon)
- REQUEST_TYPE: INBOUND (consume tokens), BURST (consume multiple), REFILL (replenish from upstream)
- PAYLOAD: key=value pairs. REFILL events include token_state=svc_alpha:X,svc_beta:Y,...

## Output Schema

### `/app/runtime/throttle_state.jsonl`

One JSON object per line, one per request:
```json
{"request_index": 0, "service": "svc_alpha", "request_type": "INBOUND", "timestamp": 100, "token_budget": {"svc_alpha": 9, "svc_beta": 0, "svc_gamma": 0, "svc_delta": 0, "svc_epsilon": 0}}
```

### `/app/runtime/throttle_report.json`

```json
{
  "service_ids": ["svc_alpha", "svc_beta", "svc_delta", "svc_epsilon", "svc_gamma"],
  "total_requests": 30,
  "requests_per_service": {"svc_alpha": 7, "svc_beta": 6, "svc_gamma": 6, "svc_delta": 6, "svc_epsilon": 5},
  "conflict_count": <int>,
  "independent_count": <int>,
  "scheduling_order": [<request indices in scheduling order>],
  "asymmetry_holds": <bool>,
  "throttle_fingerprint": "<16-char hex string>"
}
```

## Environment

- Python 3.11 available system-wide
- Global system-wide tooling: `uv` and `pytest` are available
- No external dependencies needed (stdlib only)
- Output files go in `/app/runtime/`
- Run with: `python3 /app/runtime/rate_engine.py`

## What We Need

Find and fix the bugs causing the symptoms above. The request log and parser are correct — the issues are in how tokens are replenished, how independence relationships are determined, and how the report is generated.

Two requests are considered **independent** when neither budget state dominates the other — i.e., their budget vectors are incomparable in the partial order. If budget A has some components greater and some less than budget B, neither dominates and they are independent (no scheduling constraint between them).

Don't add dependencies. Don't change the input format or output schema. Just make the numbers right.
