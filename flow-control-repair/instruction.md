# TCP Flow Control Window Manager — Incident Report

## Context

We have a flow control system that processes packet acknowledgment logs from multiple connections, applies sliding window congestion control, classifies connection pairs as contention-free or competing, and produces a congestion report. This has been running in production for months, but after a recent refactor the outputs started drifting.

## Symptoms

Our reference implementation (verified against the TCP congestion control specification) produces a known-good scheduling decomposition for the same ACK data. When we compare:

1. **Contention-free pairs are severely undercounted** — We expect hundreds of contention-free pairs (packets with incomparable window states), but the system reports almost none. It's classifying nearly everything as competing.

2. **Window states appear inconsistent** — SACK events that should advance windows are showing stale values. Connections receiving peer state are not reflecting expected post-SACK window — the receiver's own component should exceed the peer's value but instead they match exactly.

3. **The scheduling order doesn't match priority-based output** — The scheduling appears to be a simple sort by ACK arrival timestamp, which... isn't how priority scheduling works. Timestamp ordering ≠ window-priority scheduling.

4. **Fingerprint drifts between connection configurations** — The congestion fingerprint (SHA-256 of the scheduling graph structure) doesn't match the reference. This blocks our CI because we use the fingerprint for regression detection.

## System Architecture

The processing flow is:

```
ack_log.txt → ack_parser.py → window_engine.py → congestion_analyzer.py → report_writer.py
                                                                                ↓
                                                         congestion_state.jsonl + congestion_report.json
```

- `flow_engine.py` — Orchestrator. Reads packets, runs the flow, writes output. This file is fine.
- `ack_parser.py` — Parses the pipe-delimited ACK format. This file is fine.
- `window_engine.py` — Maintains congestion windows per connection with sliding window semantics.
- `congestion_analyzer.py` — Classifies all packet pairs as competing or contention-free. Computes scheduling order.
- `report_writer.py` — Writes the JSONL state file and JSON report with fingerprint.

## Input Format

The ACK log (`ack_log.txt`) uses pipe-delimited fields:

```
TIMESTAMP|CONNECTION|ACK_TYPE|PAYLOAD
```

- TIMESTAMP: milliseconds (monotonic per connection)
- CONNECTION: which connection produced the packet (conn_alpha, conn_beta, conn_gamma, conn_delta, conn_epsilon)
- ACK_TYPE: DATA (consume window), DUPLEX (consume multiple), SACK (selective ack from peer)
- PAYLOAD: key=value pairs. SACK events include peer_window=conn_alpha:X,conn_beta:Y,...

## Output Schema

### `/app/runtime/congestion_state.jsonl`

One JSON object per line, one per packet:
```json
{"packet_index": 0, "connection": "conn_alpha", "ack_type": "DATA", "timestamp": 100, "congestion_window": {"conn_alpha": 9, "conn_beta": 0, "conn_gamma": 0, "conn_delta": 0, "conn_epsilon": 0}}
```

### `/app/runtime/congestion_report.json`

```json
{
  "connection_ids": ["conn_alpha", "conn_beta", "conn_delta", "conn_epsilon", "conn_gamma"],
  "total_packets": 30,
  "packets_per_connection": {"conn_alpha": 7, "conn_beta": 6, "conn_gamma": 6, "conn_delta": 6, "conn_epsilon": 5},
  "competing_count": <int>,
  "contention_free_count": <int>,
  "scheduling_order": [<packet indices in scheduling order>],
  "asymmetry_holds": <bool>,
  "congestion_fingerprint": "<16-char hex string>"
}
```

## Environment

- Python 3.11 available system-wide
- Global system-wide tooling: `uv` and `pytest` are available
- No external dependencies needed (stdlib only)
- Output files go in `/app/runtime/`
- Run with: `python3 /app/runtime/flow_engine.py`

## What We Need

Find and fix the bugs causing the symptoms above. The ACK log and parser are correct — the issues are in how windows are advanced, how contention-free relationships are determined, and how the report is generated.

Two connections are considered **contention-free** when neither window state dominates the other — i.e., their window vectors are incomparable in the partial order. If window A has some components greater and some less than window B, neither dominates and they are contention-free (no scheduling constraint between them).

Don't add dependencies. Don't change the input format or output schema. Just make the numbers right.
