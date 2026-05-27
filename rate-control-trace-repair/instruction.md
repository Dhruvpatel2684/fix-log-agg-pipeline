# Rate Control Trace Repair

## Background

I've been debugging our congestion control trace replayer for the past day and I'm stuck. The system replays captured network packet traces through a CUBIC-like congestion control algorithm and produces statistics: bandwidth estimates, congestion window (cwnd) evolution, loss rates, and pacing metrics. We use it to validate our transport protocol implementations against known-good traces before deploying to production switches.

The replayer loads pipe-delimited trace files containing timestamped events (ACKs, losses, timeouts, probe phases) and processes them through four main components: an RTT/bandwidth estimator, a CUBIC congestion controller, a loss detector, and a pacing rate calculator.

## Symptoms

I've isolated six anomalies in the output. Each one produces results that are clearly wrong when compared against the known trace characteristics:

1. **Bandwidth estimates are in the wrong order of magnitude.** For trace_alpha (a 100 Mbps link with ~50ms RTT), the replayer reports bandwidth of approximately 30 bytes/ms instead of ~30,000 bytes/sec. The numbers are exactly 1000x too small, suggesting a unit conversion error between milliseconds and seconds somewhere in the delivery rate calculation.

2. **RTT smoothing is inverted.** The EWMA filter is weighting new samples at 87.5% instead of the RFC-specified 12.5%. This causes the smoothed RTT to track individual samples too closely, oscillating wildly instead of providing the stable filtered estimate we need for timeout computation and pacing decisions.

3. **Congestion window explodes after recovery.** After a loss event in trace_alpha, the CUBIC growth function produces a cwnd that grows far too aggressively. The post-recovery window reaches values 5-10x larger than expected within a few hundred milliseconds. This suggests the time-based growth function is operating in the wrong time unit — cubic growth with milliseconds instead of seconds would amplify the (t-K)^3 term by 10^9.

4. **Loss rate reports are systematically too low.** Trace_gamma has 4 losses among 90 observed events (86 ACKs + 4 losses), giving a true loss rate of 4/90 ≈ 4.44%. But the replayer reports approximately 2.2% — exactly half. The denominator in the loss calculation appears to be using a cumulative sequence-space counter instead of the actual observed packet outcomes.

5. **Pacing rate decreases during probe-up phases.** When the replayer enters a bandwidth probing phase (gain=1.25), the pacing rate should increase by 25% to probe for additional capacity. Instead, it drops by approximately 20%. This is consistent with the gain factor being applied as a divisor rather than a multiplier in the pacing rate formula.

6. **Post-loss multiplicative decrease is too aggressive.** After congestion events, the window drops to 50% of its pre-loss value instead of the CUBIC-specified 70%. The reduction factor appears to use TCP Reno's beta=0.5 instead of CUBIC's beta=0.7 (RFC 8312, Section 4.6).

## Architecture

The system is structured as follows:

```
runtime/
├── config.ini          — Algorithm parameters (C, beta, alpha, gains)
├── data/               — Trace files (pipe-delimited .log format)
│   ├── trace_alpha.log — Steady-state, moderate RTT (~50ms), 100 events
│   ├── trace_beta.log  — High-jitter link (30-200ms RTT), 80 events
│   ├── trace_gamma.log — Heavy loss (~5% rate), 90 events
│   └── trace_delta.log — Bandwidth probing with gain cycling, 70 events
├── estimator.py        — RTT/BW estimation (EWMA, min-filter, max-filter)
├── controller.py       — CUBIC congestion state machine
├── detector.py         — Loss/congestion detection
├── pacer.py            — Pacing rate computation
├── reporter.py         — Output generation (JSON reports)
└── run_analysis.py     — Entry point (trace loading, replay loop)
```

## Trace Format

Each trace file uses pipe-delimited fields:

```
timestamp_ms|event_type|seq_num|bytes_acked|rtt_sample_ms|extra
```

Event types: `ACK`, `LOSS`, `TIMEOUT`, `PROBE_START`, `PROBE_END`

## File Status

**Files containing defects:**
- `estimator.py` — Contains bugs #1 (EWMA direction) and #2 (bandwidth units)
- `controller.py` — Contains bugs #3 (CUBIC time unit) and #6 (beta factor)
- `detector.py` — Contains bug #4 (loss rate denominator)
- `pacer.py` — Contains bug #5 (pacing gain application)

**Files confirmed clean (no bugs):**
- `reporter.py` — Output formatting only, no algorithmic computations
- `run_analysis.py` — Entry point, trace parsing, replay orchestration

## Output Schema

Each trace produces a JSON result with these fields:

| Field | Type | Description |
|-------|------|-------------|
| `cwnd_final` | int | Final congestion window (segments) |
| `bw_estimate` | float | Filtered bandwidth estimate (bytes/sec) |
| `loss_rate` | float | Cumulative packet loss ratio (0.0-1.0) |
| `pacing_rate` | float | Current pacing rate (segments/ms) |
| `srtt` | float | Smoothed RTT estimate (ms) |
| `min_rtt` | float | Minimum observed RTT (ms) |
| `total_events` | int | Number of trace events processed |
| `ack_count` | int | ACK events processed |
| `loss_count` | int | Loss events detected |
| `congestion_events` | int | Distinct congestion epochs |
| `pacing_gain` | float | Current pacing gain factor |
| `beta_ratio` | float | Post-loss / pre-loss cwnd ratio |
| `pre_loss_cwnd` | int | Window size before last loss |
| `post_loss_cwnd` | int | Window size at end of trace |

## Expected Correct Values

After fixes, the replayer should produce:

| Trace | cwnd_final | bw_estimate | loss_rate | srtt |
|-------|-----------|-------------|-----------|------|
| alpha | ~67 | ~30,500 B/s | 0.01 | ~50ms |
| beta | ~50 | ~18,800 B/s | 0.0125 | ~81ms |
| gamma | ~12 | ~22,900 B/s | 0.0444 | ~65ms |
| delta | ~53 | ~36,900 B/s | 0.0147 | ~41ms |

## Running

```bash
cd /app
python3 -m runtime.run_analysis
```

Output is written to `/app/runtime/output/` as JSON files.
