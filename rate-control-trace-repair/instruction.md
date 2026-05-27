# Rate Control Trace Repair

## Background

We operate a network monitoring platform that replays packet acknowledgment traces through a simulated TCP CUBIC congestion control stack to produce bandwidth estimates, congestion window profiles, and link utilization reports. The system processes four captured traces from production links and generates an aggregated JSON report used by our capacity planning dashboards.

## Problem

After a recent refactoring to improve code readability, several behavioral anomalies have appeared in the analysis output. The system still runs without errors, but the metrics produced are clearly wrong when compared against known ground truth from our production environment.

## Observed Symptoms

Our operations team has flagged the following discrepancies:

1. **RTT estimation drift**: The smoothed RTT estimate diverges over time instead of converging toward the true path RTT. After processing many samples, SRTT moves further from recent observations rather than tracking them. This is visible across all four traces.

2. **Throughput magnitude anomaly**: Delivery rate estimates are reported in unexpectedly low magnitudes. The numbers appear plausible at a glance but are roughly three orders of magnitude below what the actual link capacity would produce. Dashboard alerts fire because estimated throughput doesn't match provisioned bandwidth.

3. **Sluggish window recovery**: After a loss event, the congestion window takes significantly longer to recover to its pre-loss level than expected for CUBIC. Growth during congestion avoidance is measurably slower than the theoretical CUBIC curve. The epoch duration to reach W_max appears inflated.

4. **Overshooting after loss**: The slow-start threshold appears miscalibrated after congestion events. The system re-enters slow-start and overshoots the safe window size, leading to repeated loss cascades in the loss-heavy trace.

5. **RTO too tight**: Spurious retransmission timeouts are triggered even on paths with moderate jitter. The computed RTO is barely above the smoothed RTT, leaving no safety margin for normal RTT variability.

6. **Pacing burst spikes**: The pacing engine permits larger bursts than expected. Token replenishment appears significantly faster than the intended pacing rate, causing the bucket to overflow between sends.

7. **Utilization under-reported**: The link utilization metric in the final report is pessimistic—reporting values that would imply extremely low efficiency even on traces with healthy throughput. Capacity planning flagged this as an impossibly low number for 100Mbps links.

## Architecture

The codebase lives in `environment/runtime/` with the following modules:

- `estimator.py` — RTT smoothing, bandwidth delivery rate computation
- `controller.py` — CUBIC congestion control state machine
- `detector.py` — Loss detection and RTO computation
- `pacer.py` — Token bucket pacing engine
- `reporter.py` — Statistics aggregation and report generation
- `run_analysis.py` — Entry point and trace replay loop (no issues here)
- `config.ini` — Parameters (no issues here)
- `data/` — Trace files (no issues here)

## Task

Identify and fix the bugs causing the seven behavioral anomalies described above. The issues are in the computational logic of the first five modules listed. The entry point, configuration, and data files are correct.

## Constraints

- Do not modify `run_analysis.py`, `config.ini`, or the trace data files
- Fixes should be minimal—correct the formulas without restructuring the code
- All fix targets are arithmetic/formula errors in the core computation paths
- The fixed system should produce physically plausible metrics that pass validation
