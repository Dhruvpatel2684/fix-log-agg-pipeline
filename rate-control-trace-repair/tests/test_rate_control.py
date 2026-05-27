"""
Validation test suite for rate control trace analysis.

Tests are organized in tiers:
    Tier 1: Basic structural validation (always pass)
    Tier 2: Estimation correctness (require estimator fixes)
    Tier 3: Controller behavior (require controller + detector fixes)
    Tier 4: Pacing and reporting (require pacer + reporter fixes)
"""

import os
import sys
import json
import math
import pytest

sys.path.insert(0, '/app')

from runtime.run_analysis import run_full_analysis, load_config, parse_trace_file
from runtime.estimator import RTTEstimator, DeliveryRateEstimator, CombinedEstimator
from runtime.controller import CUBICController, CongestionState
from runtime.detector import LossDetector, RTOComputer
from runtime.pacer import PacingEngine, TokenBucket
from runtime.reporter import ReportGenerator


@pytest.fixture(scope="module")
def analysis_report():
    """Run full analysis and return the report."""
    os.makedirs('/app/runtime/output', exist_ok=True)
    report = run_full_analysis('/app/runtime/config.ini')
    return report


@pytest.fixture(scope="module")
def config():
    """Load configuration."""
    return load_config('/app/runtime/config.ini')


# =============================================================================
# TIER 1: Basic Structural Validation (5 tests)
# These should always pass regardless of formula correctness.
# =============================================================================

class TestTier1Structure:
    """Basic structural and existence checks."""

    def test_output_file_exists(self, analysis_report):
        """Verify that the analysis produces an output file."""
        output_path = analysis_report.get("_output_path")
        assert output_path is not None
        assert os.path.exists(output_path)

    def test_all_traces_processed(self, analysis_report):
        """Verify all four traces are present in results."""
        trace_results = analysis_report.get("trace_results", {})
        expected = {"trace_alpha", "trace_beta", "trace_gamma", "trace_delta"}
        assert set(trace_results.keys()) == expected

    def test_event_counts_positive(self, analysis_report):
        """Verify each trace processed a positive number of events."""
        for name, result in analysis_report["trace_results"].items():
            assert result["events_processed"] > 0, f"{name} has no events"
            assert result["acks_processed"] > 0, f"{name} has no ACKs"

    def test_non_negative_metrics(self, analysis_report):
        """Verify key metrics are non-negative."""
        for name, result in analysis_report["trace_results"].items():
            assert result["final_cwnd"] >= 0, f"{name} negative cwnd"
            assert result["final_srtt"] >= 0, f"{name} negative srtt"
            assert result["max_cwnd"] >= 0, f"{name} negative max_cwnd"

    def test_report_has_required_fields(self, analysis_report):
        """Verify report structure has all required top-level fields."""
        required = ["summary", "rtt_statistics", "flows", "controller",
                    "detection", "pacing", "trace_results", "time_series"]
        for field in required:
            assert field in analysis_report, f"Missing field: {field}"


# =============================================================================
# TIER 2: Estimation Correctness (4 tests)
# Require Bug 1 (SRTT direction) and Bug 2 (delivery rate units) to be fixed.
# =============================================================================

class TestTier2Estimation:
    """RTT and bandwidth estimation correctness."""

    def test_srtt_converges_to_samples(self):
        """
        SRTT must converge toward recent RTT samples, not diverge.
        
        Initialize at one RTT then feed samples at a different value.
        A correct EWMA will converge toward the new value; incorrect
        sign will diverge away from it.
        """
        estimator = RTTEstimator(alpha=0.125, beta=0.25,
                                 initial_srtt=200.0, initial_rttvar=100.0)
        
        # First sample initializes SRTT to 200ms
        estimator.update(200.0)
        
        # Now feed 40 samples at 50ms - SRTT should converge toward 50
        target_rtt = 50.0
        for _ in range(40):
            srtt, _ = estimator.update(target_rtt)
        
        # After 40 samples with alpha=0.125, should be close to target
        assert abs(srtt - target_rtt) < 20.0, \
            f"SRTT={srtt:.1f} did not converge to target={target_rtt} (diff={abs(srtt-target_rtt):.1f})"

    def test_srtt_tracks_step_change(self):
        """
        SRTT should track a step change in RTT within reasonable time.
        
        First stabilize at one RTT, then shift to a new value.
        SRTT should adapt to the new value, not move away from it.
        """
        estimator = RTTEstimator(alpha=0.125, beta=0.25,
                                 initial_srtt=100.0, initial_rttvar=50.0)
        
        # Stabilize at 100ms
        for _ in range(30):
            estimator.update(100.0)
        
        # Step change to 50ms
        for _ in range(30):
            srtt, _ = estimator.update(50.0)
        
        # Should have moved toward 50, not away from it
        assert srtt < 80.0, \
            f"SRTT={srtt:.1f} did not track step change to 50ms"

    def test_delivery_rate_magnitude(self):
        """
        Delivery rate should be in bytes/second, not bytes/millisecond.
        
        With 1460 bytes every 10ms, expect ~146000 bytes/sec.
        If rate is ~146, it's in bytes/ms (missing *1000 conversion).
        """
        estimator = DeliveryRateEstimator(smoothing_window=8)
        
        # Simulate ACKs: 1460 bytes every 10ms
        rates = []
        for i in range(20):
            ts = 1000.0 + i * 10.0  # 10ms intervals
            rate = estimator.on_ack(ts, 1460)
            if rate is not None:
                rates.append(rate)
        
        # Should be ~146000 bytes/sec, not ~146 bytes/ms
        avg_rate = sum(rates) / len(rates) if rates else 0
        assert avg_rate > 10000.0, \
            f"Delivery rate {avg_rate:.1f} is too low - likely in wrong units (bytes/ms instead of bytes/sec)"

    def test_delivery_rate_scales_with_bandwidth(self):
        """
        Higher byte counts should produce proportionally higher rates.
        
        Verifies rate computation is using correct time base.
        """
        estimator = DeliveryRateEstimator(smoothing_window=8)
        
        # 5840 bytes (4 segments) every 20ms = 292000 bytes/sec
        rates = []
        for i in range(15):
            ts = 500.0 + i * 20.0
            rate = estimator.on_ack(ts, 5840)
            if rate is not None:
                rates.append(rate)
        
        avg_rate = sum(rates) / len(rates) if rates else 0
        # Expected: 5840/0.020 = 292000 B/s
        assert avg_rate > 100000.0, \
            f"Rate {avg_rate:.1f} too low for 5840B/20ms (expect ~292000)"
        assert avg_rate < 500000.0, \
            f"Rate {avg_rate:.1f} too high for 5840B/20ms (expect ~292000)"


# =============================================================================
# TIER 3: Controller Behavior (4 tests)
# Require Bug 3 (CUBIC K), Bug 4 (ssthresh), Bug 5 (RTO) to be fixed.
# =============================================================================

class TestTier3Controller:
    """CUBIC congestion control behavior validation."""

    def test_cwnd_bounded_after_loss(self):
        """
        CUBIC K value must account for beta reduction factor.
        
        After loss, K determines how long until cwnd reaches W_max.
        K = cbrt(W_max*(1-beta)/C). If (1-beta) is missing, K is too
        large, making the cubic function grow too slowly from the
        reduced window, and the time-to-recover is excessive.
        """
        config = {"C": 0.4, "beta": 0.7, "initial_cwnd": 10}
        controller = CUBICController(config)
        
        # Grow to a good window
        for i in range(80):
            controller.on_ack(i * 50.0, 1460, 50.0, 45.0)
        
        pre_loss_cwnd = controller.cwnd
        
        # Trigger loss - this sets K
        controller.on_loss(4000.0, 50)
        
        # K should be cbrt(W_max * (1-beta) / C) = cbrt(W_max * 0.3 / 0.4)
        # With bug: K = cbrt(W_max / C) which is much larger
        # Correct K for W_max~90: cbrt(90*0.3/0.4) = cbrt(67.5) ~ 4.07
        # Buggy K: cbrt(90/0.4) = cbrt(225) ~ 6.08
        
        # The K value determines recovery slope.
        # After 3 seconds of congestion avoidance, with correct K,
        # the cubic function produces reasonable growth.
        # Manually test the cubic function at t=K (should equal W_max)
        import math
        C = 0.4
        K = controller._K
        w_max = controller._w_max
        
        # At t=K, W(K) = C*(K-K)^3 + W_max = W_max (this is always true)
        # At t=0, W(0) = C*(0-K)^3 + W_max = W_max - C*K^3
        # This should equal beta*W_max = 0.7*W_max
        w_at_zero = C * (0 - K)**3 + w_max
        expected_w_at_zero = 0.7 * w_max
        
        # With correct K: w_at_zero should be approximately beta*W_max
        # With buggy K: w_at_zero will be much lower (even negative)
        assert w_at_zero > 0, \
            f"W(0)={w_at_zero:.1f} is negative - K is too large"
        assert abs(w_at_zero - expected_w_at_zero) < 0.2 * w_max, \
            f"W(0)={w_at_zero:.1f} should be ~{expected_w_at_zero:.1f} (beta*W_max)"

    def test_ssthresh_less_than_cwnd_at_loss(self):
        """
        After loss, ssthresh should be beta * cwnd, not cwnd itself.
        
        Setting ssthresh = cwnd causes slow-start to overshoot because
        it doesn't exit until reaching the old (too high) window.
        """
        config = {"C": 0.4, "beta": 0.7, "initial_cwnd": 10}
        controller = CUBICController(config)
        
        # Grow window
        for i in range(80):
            controller.on_ack(i * 50.0, 1460, 50.0, 45.0)
        
        pre_loss_cwnd = controller.cwnd
        
        # Trigger loss
        controller.on_loss(4000.0, 40)
        
        # ssthresh should be less than pre_loss_cwnd (it should be beta*cwnd)
        assert controller.ssthresh < pre_loss_cwnd, \
            f"ssthresh={controller.ssthresh:.1f} should be < pre_loss_cwnd={pre_loss_cwnd:.1f}"
        
        # More specifically, should be approximately beta * pre_loss_cwnd
        expected_ssthresh = pre_loss_cwnd * 0.7
        tolerance = pre_loss_cwnd * 0.15  # Allow some tolerance
        assert abs(controller.ssthresh - expected_ssthresh) < tolerance, \
            f"ssthresh={controller.ssthresh:.1f} not close to beta*cwnd={expected_ssthresh:.1f}"

    def test_rto_includes_variance_multiplier(self):
        """
        RTO must include the 4x RTTVAR safety margin per RFC 6298.
        
        RTO = SRTT + max(G, 4*RTTVAR), not SRTT + RTTVAR.
        Without the multiplier, RTO is too tight and causes spurious timeouts.
        """
        rto_comp = RTOComputer(granularity_ms=1.0, min_rto_ms=10.0)
        
        srtt = 200.0    # 200ms smoothed RTT
        rttvar = 50.0   # 50ms variance
        
        rto = rto_comp.compute(srtt, rttvar)
        
        # Correct: 200 + max(1, 4*50) = 200 + 200 = 400ms
        # Buggy:   200 + 50 = 250ms (too tight)
        assert rto >= 380.0, \
            f"RTO={rto:.1f}ms too tight (expected ~400ms for SRTT=200, RTTVAR=50)"

    def test_rto_safe_with_high_variance(self):
        """
        High RTTVAR should produce a conservative RTO.
        
        Verifies the 4x multiplier is applied to variance, providing
        adequate safety margin for jittery paths.
        """
        rto_comp = RTOComputer(granularity_ms=1.0, min_rto_ms=10.0)
        
        srtt = 150.0     # 150ms smoothed RTT
        rttvar = 80.0   # 80ms variance (high jitter)
        
        rto = rto_comp.compute(srtt, rttvar)
        
        # Correct: 150 + max(1, 4*80) = 150 + 320 = 470ms
        # Buggy:   150 + 80 = 230ms
        assert rto >= 400.0, \
            f"RTO={rto:.1f}ms dangerously tight for high-jitter path (expected ~470)"


# =============================================================================
# TIER 4: Pacing and Reporting (2 tests)
# Require Bug 6 (pacing time units) and Bug 7 (bits/bytes) to be fixed.
# =============================================================================

class TestTier4PacingReporting:
    """Pacing rate and utilization reporting correctness."""

    def test_pacing_token_rate_correct(self):
        """
        Token replenishment rate must match pacing rate units.
        
        If pacing_rate is in segments/second but elapsed is in ms,
        tokens accumulate 1000x too fast without proper conversion.
        """
        config = {"default_gain": 1.0, "probe_gain": 1.25}
        pacer = PacingEngine(config)
        
        # Set rate for cwnd=100, RTT=100ms => 1000 seg/sec
        pacer.update_rate(cwnd=100.0, rtt_ms=100.0, timestamp_ms=0.0)
        rate = pacer.pacing_rate
        
        # Rate should be 1000 segments/sec
        assert 800.0 < rate < 1200.0, f"Pacing rate {rate} unexpected"
        
        # Now check token accumulation over 10ms
        bucket = TokenBucket(capacity=100.0, initial_tokens=0.0)
        # 10ms at 1000 seg/sec should add 10 tokens
        tokens_added = bucket.refill(10.0, rate)
        
        # Correct: 10ms * (1000/1000) = 10 tokens (with /1000 conversion)
        # Buggy: 10ms * 1000 = 10000 tokens (way too many)
        assert tokens_added <= 20.0, \
            f"Token replenishment {tokens_added:.1f} too fast (expected ~10 for 10ms at 1000seg/s)"

    def test_link_utilization_plausible(self, analysis_report):
        """
        Link utilization must be physically plausible (> 0.5 for healthy traces).
        
        A 100Mbps link = 12.5 MB/sec. If code treats Mbps as MBps (missing /8),
        reported utilization will be 8x too low (pessimistic).
        """
        utilization = analysis_report["summary"]["link_utilization"]
        
        # With realistic traces on a 100Mbps link, utilization should be
        # reasonable. The bits/bytes confusion makes it 8x too low.
        # Even modest traffic should show > 0.01 utilization.
        # With correct calculation, our traces produce ~0.05-0.3
        # With bug (missing /8), they produce ~0.006-0.04
        
        # The key test: utilization should not be impossibly low
        # We test that it's at least 0.02 (2% of 12.5MB/s capacity)
        assert utilization > 0.02, \
            f"Utilization {utilization:.4f} impossibly low for 100Mbps link - check bits/bytes conversion"
