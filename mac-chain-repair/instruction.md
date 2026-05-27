# MAC Chain Verification — Incident Report

## Context

We have a distributed MAC verification system that processes authentication logs from multiple signing authorities, validates hash chain states, classifies authority pairs as non-conflicting or conflicting based on their chain state vectors, and produces a verification report. This has been running in production for months, but after a recent refactor the outputs started drifting.

## Symptoms

Our reference implementation (verified against the hash chain attestation specification) produces a known-good verification decomposition for the same auth data. When we compare:

1. **Non-conflicting pairs are severely undercounted** — We expect hundreds of non-conflicting pairs (events with incomparable chain states), but the system reports almost none. It's classifying nearly everything as conflicting.

2. **Chain states appear inconsistent — SYNC events that should advance chains are showing stale values. Authorities receiving peer state are not reflecting expected post-SYNC depth — the receiver's own component should exceed the peer's value but instead they match exactly.**

3. **The verification order doesn't match priority-based output** — The ordering appears to be a simple sort by attestation timestamp, which... isn't how priority verification works. Timestamp ordering ≠ chain-depth-priority verification.

4. **Fingerprint drifts between authority configurations** — The chain fingerprint (SHA-256 of the verification graph structure) doesn't match the reference. This blocks our CI because we use the fingerprint for regression detection.

## System Architecture

The processing flow is:

```
auth_log.txt → auth_parser.py → chain_engine.py → integrity_analyzer.py → report_writer.py
                                                                                ↓
                                                         chain_state.jsonl + chain_report.json
```

- `mac_engine.py` — Orchestrator. Reads events, runs the flow, writes output. This file is fine.
- `auth_parser.py` — Parses the pipe-delimited auth format. This file is fine.
- `chain_engine.py` — Maintains chain depth vectors per authority with hash chain semantics.
- `integrity_analyzer.py` — Classifies all event pairs as conflicting or non-conflicting. Computes verification order.
- `report_writer.py` — Writes the JSONL state file and JSON report with fingerprint.

## Input Format

The auth log (`/app/runtime/auth_log.txt`) uses pipe-delimited fields:

```
TIMESTAMP|AUTHORITY|MSG_TYPE|PAYLOAD
```

- TIMESTAMP: milliseconds (monotonic per authority)
- AUTHORITY: which signing authority produced the event (auth_alpha, auth_beta, auth_gamma, auth_delta, auth_epsilon)
- MSG_TYPE: SIGN (single attestation), BATCH (multi-attestation), SYNC (peer chain merge)
- PAYLOAD: key=value pairs. SYNC events include peer_chain=auth_alpha:X,auth_beta:Y,...

## Output Schema

### `/app/runtime/chain_state.jsonl`

One JSON object per line, one per event:
```json
{"event_index": 0, "authority": "auth_alpha", "msg_type": "SIGN", "timestamp": 100, "chain_depth": {"auth_alpha": 9, "auth_beta": 0, "auth_gamma": 0, "auth_delta": 0, "auth_epsilon": 0}}
```

### `/app/runtime/chain_report.json`

```json
{
  "authority_ids": ["auth_alpha", "auth_beta", "auth_delta", "auth_epsilon", "auth_gamma"],
  "total_events": 30,
  "events_per_authority": {"auth_alpha": 7, "auth_beta": 6, "auth_gamma": 6, "auth_delta": 6, "auth_epsilon": 5},
  "conflict_count": <int>,
  "non_conflicting_count": <int>,
  "verification_order": [<event indices in verification order>],
  "asymmetry_holds": <bool>,
  "chain_fingerprint": "<16-char hex string>"
}
```

## Environment

- Python 3.11 available system-wide
- Global system-wide tooling: `uv` and `pytest` are available
- No external dependencies needed (stdlib only)
- Output files go in `/app/runtime/`
- Run with: `python3 /app/runtime/mac_engine.py`

## What We Need

Find and fix the bugs causing the symptoms above. The auth log and parser are correct — the issues are in how chains are advanced, how non-conflicting relationships are determined, and how the report is generated.

Two events are considered **non-conflicting** when neither chain state dominates the other — i.e., their chain depth vectors are incomparable in the partial order. If chain A has some components greater and some less than chain B, neither dominates and they are non-conflicting (no verification constraint between them).

Don't add dependencies. Don't change the input format or output schema. Just make the numbers right.
