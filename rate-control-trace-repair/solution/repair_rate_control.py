#!/usr/bin/env python3
"""Repair script for rate control trace replayer.

Patches six defects in the congestion control modules:
1. EWMA smoothing factor direction (estimator.py)
2. Bandwidth unit conversion ms->sec (estimator.py)
3. CUBIC elapsed time unit ms->sec (controller.py)
4. Loss rate denominator formula (detector.py)
5. Pacing gain application direction (pacer.py)
6. CUBIC multiplicative decrease beta factor (controller.py)
"""

import subprocess
import sys


def patch_estimator():
    """Fix RTT and bandwidth estimation bugs."""
    path = "/app/runtime/estimator.py"
    with open(path) as f:
        content = f.read()

    # Fix Bug 1: EWMA alpha direction
    # RFC 6298: SRTT = (1-alpha)*SRTT + alpha*R' where alpha weights NEW sample
    content = content.replace(
        "self._srtt = self._alpha * self._srtt + (1 - self._alpha) * rtt_sample",
        "self._srtt = (1 - self._alpha) * self._srtt + self._alpha * rtt_sample"
    )

    # Fix Bug 2: bandwidth units (ms -> sec)
    # Bandwidth is bytes/sec; RTT is in ms so must divide by (rtt_ms/1000)
    content = content.replace(
        "bw_sample = bytes_delivered / rtt_ms",
        "bw_sample = bytes_delivered / (rtt_ms / 1000.0)"
    )

    with open(path, "w") as f:
        f.write(content)


def patch_controller():
    """Fix CUBIC growth and beta factor bugs."""
    path = "/app/runtime/controller.py"
    with open(path) as f:
        content = f.read()

    # Fix Bug 3: CUBIC time in seconds
    # RFC 8312 specifies t in seconds; using ms gives (t-K)^3 that's 10^9 too large
    content = content.replace(
        "elapsed = current_time_ms - self._epoch_start_ms",
        "elapsed = (current_time_ms - self._epoch_start_ms) / 1000.0"
    )

    # Fix Bug 6: CUBIC beta 0.7, not 0.5
    # RFC 8312 Section 4.6: beta_cubic = 0.7 (not Reno's 0.5)
    content = content.replace(
        "new_cwnd = int(self._cwnd * 0.5)",
        "new_cwnd = int(self._cwnd * 0.7)"
    )

    with open(path, "w") as f:
        f.write(content)


def patch_detector():
    """Fix loss rate computation bug."""
    path = "/app/runtime/detector.py"
    with open(path) as f:
        content = f.read()

    # Fix Bug 4: loss rate denominator
    # Correct: lost / (lost + acked) in measurement window, not cumulative total_sent
    content = content.replace(
        "loss_rate = self._lost_count / self._total_sent",
        "loss_rate = self._lost_count / (self._lost_count + self._acked_count)"
    )

    with open(path, "w") as f:
        f.write(content)


def patch_pacer():
    """Fix pacing gain application bug."""
    path = "/app/runtime/pacer.py"
    with open(path) as f:
        content = f.read()

    # Fix Bug 5: pacing gain multiplies numerator, not denominator
    # BBR-style: pacing_rate = cwnd * gain / RTT (gain speeds up probing)
    content = content.replace(
        "pacing_rate = self._cwnd / (self._pacing_gain * srtt)",
        "pacing_rate = (self._cwnd * self._pacing_gain) / srtt"
    )

    with open(path, "w") as f:
        f.write(content)


def main():
    """Apply all patches and re-run analysis."""
    patch_estimator()
    patch_controller()
    patch_detector()
    patch_pacer()

    # Re-run analysis with corrected code
    subprocess.run(
        [sys.executable, "-m", "runtime.run_analysis"],
        cwd="/app",
        check=True
    )


if __name__ == "__main__":
    main()
