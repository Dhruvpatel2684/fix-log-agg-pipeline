"""
Repair script for rate control trace analysis pipeline.

Applies targeted fixes to computational formulas in the runtime modules.
Each fix corrects a specific arithmetic/formula error while preserving
the overall code structure.
"""

import os


def apply_fix(filepath: str, old: str, new: str, description: str):
    """Apply a single string replacement fix."""
    with open(filepath, 'r') as f:
        content = f.read()

    if old not in content:
        print(f"WARNING: Could not find target for fix: {description}")
        print(f"  File: {filepath}")
        return False

    content = content.replace(old, new, 1)

    with open(filepath, 'w') as f:
        f.write(content)

    print(f"FIXED: {description}")
    return True


def main():
    runtime_dir = "/app/runtime"

    # =========================================================================
    # Fix 1: estimator.py - SRTT EWMA direction
    # The signed error in the EWMA must be (sample - estimate), not
    # (estimate - sample). With the wrong sign, SRTT moves away from
    # the sample instead of toward it.
    # =========================================================================
    apply_fix(
        os.path.join(runtime_dir, "estimator.py"),
        "self._srtt = self._srtt + self._alpha * (self._srtt - rtt_sample)",
        "self._srtt = self._srtt + self._alpha * (rtt_sample - self._srtt)",
        "SRTT EWMA update direction (estimator.py)"
    )

    # =========================================================================
    # Fix 2: estimator.py - Delivery rate time unit conversion
    # Rate must be converted from bytes/ms to bytes/sec by multiplying
    # by 1000. Without this, rates are 1000x too low.
    # =========================================================================
    apply_fix(
        os.path.join(runtime_dir, "estimator.py"),
        "delivery_rate = bytes_delivered / elapsed_ms",
        "delivery_rate = bytes_delivered / elapsed_ms * 1000.0",
        "Delivery rate ms-to-sec conversion (estimator.py)"
    )

    # =========================================================================
    # Fix 3: controller.py - CUBIC K computation
    # K = cbrt(W_max * (1-beta) / C), not cbrt(W_max / C).
    # The (1-beta) factor accounts for the gap between the reduced window
    # (beta*W_max) and the target (W_max). Without it, K is too large
    # and recovery is too slow.
    # =========================================================================
    apply_fix(
        os.path.join(runtime_dir, "controller.py"),
        "self._K = (self._w_max / self._C) ** (1.0 / 3.0)",
        "self._K = (self._w_max * (1 - self._beta) / self._C) ** (1.0 / 3.0)",
        "CUBIC K computation with (1-beta) factor (controller.py)"
    )

    # =========================================================================
    # Fix 4: controller.py - ssthresh after loss
    # ssthresh should be beta*cwnd (the reduced window), not cwnd itself.
    # Setting ssthresh = cwnd means slow-start won't exit until reaching
    # the old (too high) window, causing overshoot.
    # =========================================================================
    apply_fix(
        os.path.join(runtime_dir, "controller.py"),
        "self._ssthresh = self._cwnd",
        "self._ssthresh = max(int(self._cwnd * self._beta), 2)",
        "ssthresh = beta*cwnd after loss (controller.py)"
    )

    # =========================================================================
    # Fix 5: detector.py - RTO formula missing 4x variance multiplier
    # RFC 6298: RTO = SRTT + max(G, 4*RTTVAR)
    # The code computes SRTT + RTTVAR (missing the K=4 multiplier and
    # the max with granularity).
    # =========================================================================
    apply_fix(
        os.path.join(runtime_dir, "detector.py"),
        "self._current_rto = srtt + rttvar",
        "self._current_rto = srtt + max(self._granularity, 4 * rttvar)",
        "RTO 4x variance multiplier per RFC 6298 (detector.py)"
    )

    # =========================================================================
    # Fix 6: pacer.py - Token bucket refill time conversion
    # Pacing rate is in segments/second, but elapsed is in milliseconds.
    # Must divide elapsed by 1000 to convert to seconds before multiplying
    # by rate. Without this, tokens accumulate 1000x too fast.
    # =========================================================================
    apply_fix(
        os.path.join(runtime_dir, "pacer.py"),
        "tokens_added = elapsed_ms * rate",
        "tokens_added = (elapsed_ms / 1000.0) * rate",
        "Token refill ms-to-sec conversion (pacer.py)"
    )

    # =========================================================================
    # Fix 7: reporter.py - Link capacity bits-to-bytes conversion
    # Link rate is in Megabits/sec. To get bytes/sec, must divide by 8.
    # 100 Mbps = 12.5 MB/sec, not 100 MB/sec. Without /8, utilization
    # is reported 8x too low.
    # =========================================================================
    apply_fix(
        os.path.join(runtime_dir, "reporter.py"),
        "capacity_bytes_sec = self._link_rate_mbps * 1000000",
        "capacity_bytes_sec = self._link_rate_mbps * 1000000 / 8",
        "Mbps to bytes/sec conversion (reporter.py)"
    )

    print("\nAll 7 fixes applied successfully.")


if __name__ == "__main__":
    main()
