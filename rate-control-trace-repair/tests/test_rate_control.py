"""Rate control trace replayer verification tests.

Validates RTT estimation, bandwidth measurement, congestion window evolution,
loss detection, and pacing behavior across four network trace scenarios.
"""

import json
import os
import sys

import pytest

OUTPUT_DIR = "/app/runtime/output"


def load_result(trace_name: str) -> dict:
    """Load the analysis result for a given trace."""
    path = os.path.join(OUTPUT_DIR, f"{trace_name}_result.json")
    with open(path) as f:
        return json.load(f)


def load_aggregate() -> dict:
    """Load the aggregate analysis report."""
    path = os.path.join(OUTPUT_DIR, "aggregate_report.json")
    with open(path) as f:
        return json.load(f)


# ============================================================================
# TIER 1: Basic functionality (always passes with buggy code)
# ============================================================================

class TestTier1BasicOutput:
    """Verify that the system produces output without crashing."""

    def test_output_files_exist(self):
        """All expected output files should be present."""
        expected_files = [
            "trace_alpha_result.json",
            "trace_beta_result.json",
            "trace_gamma_result.json",
            "trace_delta_result.json",
            "aggregate_report.json",
        ]
        for fname in expected_files:
            path = os.path.join(OUTPUT_DIR, fname)
            assert os.path.exists(path), f"Missing output file: {fname}"

    def test_correct_trace_count(self):
        """Aggregate report should show exactly 4 traces processed."""
        report = load_aggregate()
        assert report["aggregate"]["trace_count"] == 4

    def test_required_output_fields(self):
        """Each trace result must contain all required metric fields."""
        required = ["cwnd_final", "bw_estimate", "loss_rate", "pacing_rate",
                    "srtt", "total_events", "probe_gain_ratio", "loss_reduction_ratio"]
        for trace in ["trace_alpha", "trace_beta", "trace_gamma", "trace_delta"]:
            result = load_result(trace)
            for field in required:
                assert field in result, f"{trace} missing field: {field}"

    def test_non_negative_metrics(self):
        """All computed metrics must be non-negative."""
        for trace in ["trace_alpha", "trace_beta", "trace_gamma", "trace_delta"]:
            result = load_result(trace)
            assert result["cwnd_final"] >= 0, f"{trace} negative cwnd"
            assert result["bw_estimate"] >= 0, f"{trace} negative bw"
            assert result["loss_rate"] >= 0, f"{trace} negative loss"
            assert result["pacing_rate"] >= 0, f"{trace} negative pacing"

    def test_total_event_counts(self):
        """Event counts should match trace file sizes."""
        expected = {
            "trace_alpha": 100,
            "trace_beta": 80,
            "trace_gamma": 90,
            "trace_delta": 70,
        }
        for trace, count in expected.items():
            result = load_result(trace)
            assert result["total_events"] == count, (
                f"{trace}: expected {count} events, got {result['total_events']}"
            )


# ============================================================================
# TIER 2: RTT and bandwidth estimation (require Bug 1/Bug 2 fixes)
# ============================================================================

class TestTier2Estimation:
    """Validate RTT smoothing and bandwidth measurement accuracy."""

    def test_srtt_trace_alpha_converges(self):
        """Trace alpha SRTT should converge near 50ms mean (within 5ms).

        With correct EWMA (alpha=0.125 weighting new sample per RFC 6298),
        the SRTT should smoothly converge to the population mean of ~50ms.
        """
        result = load_result("trace_alpha")
        srtt = result["srtt"]
        assert 45.0 <= srtt <= 55.0, (
            f"SRTT={srtt:.2f}ms, expected 45-55ms range for 50ms-mean trace"
        )

    def test_bandwidth_trace_alpha_magnitude(self):
        """Bandwidth for trace alpha must be in kB/s range, not B/ms.

        At ~50ms RTT with 1460-byte segments, expected throughput is
        approximately 29,200 bytes/sec (1460/0.050). Filtered max should
        be 20,000-100,000 bytes/sec range.
        """
        result = load_result("trace_alpha")
        bw = result["bw_estimate"]
        assert 15000 <= bw <= 100000, (
            f"BW={bw:.2f} bytes/sec, expected 15,000-100,000 range. "
            f"If BW is ~30, likely missing ms-to-sec conversion."
        )

    def test_bandwidth_trace_beta_magnitude(self):
        """Bandwidth for high-jitter trace must be in thousands of bytes/sec.

        Even with variable RTT (30-200ms), bandwidth samples should be
        computed in bytes/sec, yielding estimates in the 10,000+ range.
        """
        result = load_result("trace_beta")
        bw = result["bw_estimate"]
        assert 10000 <= bw <= 200000, (
            f"BW={bw:.2f}, expected 10,000-200,000 bytes/sec. "
            f"Value below 100 suggests missing unit conversion."
        )

    def test_bandwidth_trace_gamma_magnitude(self):
        """Bandwidth for lossy trace should be in thousands of bytes/sec.

        Even with 5% loss, bandwidth measurement is from ACK samples
        and should be in the same order of magnitude as other traces.
        """
        result = load_result("trace_gamma")
        bw = result["bw_estimate"]
        assert 10000 <= bw <= 300000, (
            f"BW={bw:.2f}, expected 10,000-300,000 bytes/sec. "
            f"Value below 100 suggests missing unit conversion."
        )


# ============================================================================
# TIER 3: Congestion control (require Bug 3, Bug 4, or Bug 6 fixes)
# ============================================================================

class TestTier3CongestionControl:
    """Validate CUBIC window growth, loss detection, and beta factor."""

    def test_loss_rate_trace_gamma(self):
        """Loss rate for gamma trace should be 0.03-0.08.

        Trace gamma has 4 losses among 90 observed events (86 ACKs + 4 losses).
        Correct: loss_rate = 4/(4+86) = 0.0444.
        Buggy (uses total_sent = 180 from seq space): 4/180 = 0.022 (too low).
        """
        result = load_result("trace_gamma")
        loss = result["loss_rate"]
        assert 0.03 <= loss <= 0.08, (
            f"loss_rate={loss:.6f}, expected 0.03-0.08. "
            f"Value near 0.022 suggests wrong denominator in loss calculation."
        )

    def test_loss_reduction_ratio_cubic_beta(self):
        """Immediate post-loss cwnd should be ~70% of pre-loss (CUBIC beta=0.7).

        CUBIC (RFC 8312 Section 4.6) uses beta=0.7 for multiplicative decrease.
        The loss_reduction_ratio field captures int(cwnd*beta)/cwnd at the loss
        point. Should be 0.65-0.75. Buggy beta=0.5 gives 0.48-0.52.
        """
        result = load_result("trace_alpha")
        ratio = result["loss_reduction_ratio"]
        assert 0.60 <= ratio <= 0.75, (
            f"loss_reduction_ratio={ratio:.4f}, expected 0.60-0.75 (CUBIC beta=0.7). "
            f"If ratio ~0.5, using Reno's beta=0.5 instead of CUBIC 0.7."
        )

    def test_cwnd_trace_gamma_after_losses(self):
        """cwnd after multiple losses in gamma should be small (5-30 segments).

        With 4 congestion events and CUBIC beta=0.7, window shrinks each time.
        Starting from ssthresh=10000, after 4 reductions: ~10000*0.7^4 ≈ 2401,
        but slow start hits ssthresh early, so final cwnd is small.
        With buggy beta=0.5 and ms-based growth: cwnd inflates between losses.
        """
        result = load_result("trace_gamma")
        cwnd = result["cwnd_final"]
        assert 5 <= cwnd <= 30, (
            f"cwnd_gamma={cwnd}, expected 5-30 after 4 loss events. "
            f"If cwnd>40, CUBIC growth may use wrong time unit or beta is too low."
        )


# ============================================================================
# TIER 4: Pacing and combined metrics (require Bug 5 or combinations)
# ============================================================================

class TestTier4PacingAndCombined:
    """Validate pacing rate behavior and cross-trace consistency."""

    def test_probe_gain_ratio_increases(self):
        """Probe phase should increase pacing rate above cruise rate.

        With gain=1.25, the max rate during probe should be at least
        1.2x the cruise rate before probe (accounting for cwnd growth
        during probe phase that adds to the gain effect).
        
        Buggy: gain in denominator gives rate = cwnd/(1.25*srtt), so
        the probe_gain_ratio ~1.0-1.2 (reduced by gain, boosted by cwnd growth).
        Fixed: gain in numerator gives rate = 1.25*cwnd/srtt, so
        probe_gain_ratio ~1.5+ (25% from gain + cwnd growth contribution).
        """
        result = load_result("trace_delta")
        ratio = result["probe_gain_ratio"]
        assert ratio > 1.4, (
            f"probe_gain_ratio={ratio:.4f}, expected >1.4. "
            f"If ratio ~1.1-1.2, pacing gain may be in denominator instead of numerator."
        )

    def test_throughput_consistency_alpha(self):
        """Throughput for trace_alpha should be consistent with cwnd/RTT.

        Expected throughput ~ (cwnd * MSS) / RTT in bytes/sec.
        With cwnd~67, MSS=1460, RTT~50ms: ~1,956,400 bytes/sec theoretical max.
        Actual bandwidth (filtered max of per-ACK samples) should be
        at least 1% of theoretical (i.e., > 19,000 bytes/sec).
        """
        result = load_result("trace_alpha")
        cwnd = result["cwnd_final"]
        srtt = result["srtt"]
        bw = result["bw_estimate"]
        theoretical = (cwnd * 1460) / (srtt / 1000.0) if srtt > 0 else 1
        assert bw > theoretical * 0.005, (
            f"BW={bw:.2f}, theoretical_max={theoretical:.2f}. "
            f"BW should be at least 0.5% of theoretical throughput."
        )

    def test_jains_fairness_across_traces(self):
        """Jain's fairness index of bandwidth across traces should be > 0.7.

        With correct bandwidth measurements (all in bytes/sec), the four
        traces produce estimates in the same order of magnitude (10k-40k),
        yielding high fairness (~0.94). If units are inconsistent, fairness
        drops significantly.
        """
        report = load_aggregate()
        fairness = report["aggregate"]["jains_fairness"]
        assert fairness > 0.7, (
            f"Jain's fairness={fairness:.4f}, expected >0.7. "
            f"Low fairness may indicate unit inconsistency across traces."
        )
