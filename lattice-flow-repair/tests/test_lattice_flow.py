"""
Test suite for the anomaly correlation engine.
Validates classification accuracy, metric scores, and aggregation behavior
across multiple trace datasets.
"""

import sys
import json
sys.path.insert(0, "/app")

from runtime.graph import ServiceDependencyGraph
from runtime.events import EventTimeline, AnomalyEvent, GroundTruthLabels
from runtime.correlator import CorrelationEngine, correlate_trace
from runtime.aggregator import CorrelationAggregator
from runtime.metrics import MetricsEvaluator, quick_evaluate


def load_trace(name):
    """Load a trace dataset by name."""
    filepath = f"/app/runtime/data/trace_{name}.json"
    with open(filepath, "r") as f:
        data = json.load(f)
    graph = ServiceDependencyGraph.from_dict(data["graph"])
    timeline = EventTimeline()
    for event_data in data["events"]:
        timeline.add(AnomalyEvent.from_dict(event_data))
    ground_truth = GroundTruthLabels.from_list(data["ground_truth"])
    return graph, timeline, ground_truth


def run_correlation(graph, timeline, window_ms=30000):
    """Run the correlation engine and return results."""
    engine = CorrelationEngine(graph=graph, window_ms=window_ms)
    results = engine.correlate_events(timeline)
    return engine, results


# === ALPHA TRACE TESTS ===

class TestAlphaTraceClassification:
    """Test correct classification of event pairs in trace_alpha."""

    def test_alpha_gateway_to_auth_causal(self):
        """Gateway anomaly at t=1000 should cause auth_svc anomaly at t=1250."""
        graph, timeline, gt = load_trace("alpha")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("alpha_e01", "alpha_e02")
        assert result is not None
        assert result.classification == "causal", (
            f"Expected alpha_e01->alpha_e02 to be causal, got {result.classification}"
        )

    def test_alpha_order_to_payment_causal(self):
        """Order service anomaly should cause payment service anomaly."""
        graph, timeline, gt = load_trace("alpha")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("alpha_e03", "alpha_e05")
        assert result is not None
        assert result.classification == "causal", (
            f"Expected alpha_e03->alpha_e05 to be causal, got {result.classification}"
        )

    def test_alpha_timing_independent_gateway_inventory(self):
        """Gateway at t=5000 and inventory at t=5050 are independent (insufficient propagation time)."""
        graph, timeline, gt = load_trace("alpha")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("alpha_e08", "alpha_e09")
        assert result is not None
        assert result.classification == "independent", (
            f"Expected alpha_e08->alpha_e09 to be independent, got {result.classification}"
        )

    def test_alpha_timing_independent_gateway_notification(self):
        """Gateway at t=5000 and notification at t=5100 are independent (path too slow)."""
        graph, timeline, gt = load_trace("alpha")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("alpha_e08", "alpha_e10")
        assert result is not None
        assert result.classification == "independent", (
            f"Expected alpha_e08->alpha_e10 to be independent, got {result.classification}"
        )

    def test_alpha_timing_independent_gateway_payment(self):
        """Gateway at t=5000 and payment at t=5080 are independent (timing prevents causation)."""
        graph, timeline, gt = load_trace("alpha")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("alpha_e08", "alpha_e11")
        assert result is not None
        assert result.classification == "independent", (
            f"Expected alpha_e08->alpha_e11 to be independent, got {result.classification}"
        )


# === BETA TRACE TESTS ===

class TestBetaTraceClassification:
    """Test correct classification of event pairs in trace_beta."""

    def test_beta_api_to_user_causal(self):
        """API gateway anomaly should cause user service anomaly."""
        graph, timeline, gt = load_trace("beta")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("beta_e01", "beta_e02")
        assert result is not None
        assert result.classification == "causal", (
            f"Expected beta_e01->beta_e02 to be causal, got {result.classification}"
        )

    def test_beta_timing_independent_product_to_recommendation(self):
        """Product at t=2250 and recommendation at t=2400 are independent (propagation takes 500ms)."""
        graph, timeline, gt = load_trace("beta")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("beta_e03", "beta_e06")
        assert result is not None
        assert result.classification == "independent", (
            f"Expected beta_e03->beta_e06 to be independent, got {result.classification}"
        )

    def test_beta_timing_independent_search_to_recommendation(self):
        """Search at t=2350 and recommendation at t=2400 are independent (needs 450ms, only 50ms elapsed)."""
        graph, timeline, gt = load_trace("beta")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("beta_e05", "beta_e06")
        assert result is not None
        assert result.classification == "independent", (
            f"Expected beta_e05->beta_e06 to be independent, got {result.classification}"
        )

    def test_beta_timing_independent_recommendation_to_analytics(self):
        """Recommendation at t=2400 and analytics at t=2500: needs 600ms, only 100ms elapsed."""
        graph, timeline, gt = load_trace("beta")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("beta_e06", "beta_e07")
        assert result is not None
        assert result.classification == "independent", (
            f"Expected beta_e06->beta_e07 to be independent, got {result.classification}"
        )

    def test_beta_cascade_gateway_independent_of_downstream(self):
        """After CDN causes gateway, gateway at t=6050 cannot cause user_svc at t=6080 (needs 180ms)."""
        graph, timeline, gt = load_trace("beta")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("beta_e09", "beta_e10")
        assert result is not None
        assert result.classification == "independent", (
            f"Expected beta_e09->beta_e10 to be independent, got {result.classification}"
        )

    def test_beta_cdn_independent_of_analytics(self):
        """CDN at t=10000 and analytics at t=10030: no timing-feasible path."""
        graph, timeline, gt = load_trace("beta")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("beta_e16", "beta_e17")
        assert result is not None
        assert result.classification == "independent", (
            f"Expected beta_e16->beta_e17 to be independent, got {result.classification}"
        )


# === GAMMA TRACE TESTS ===

class TestGammaTraceClassification:
    """Test correct classification of event pairs in trace_gamma."""

    def test_gamma_lb_to_frontend_causal(self):
        """Load balancer at t=3000 should cause frontend at t=3150 (delay=100ms, elapsed=150ms)."""
        graph, timeline, gt = load_trace("gamma")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("gamma_e01", "gamma_e02")
        assert result is not None
        assert result.classification == "causal", (
            f"Expected gamma_e01->gamma_e02 to be causal, got {result.classification}"
        )

    def test_gamma_timing_independent_checkout_to_fulfillment(self):
        """Checkout at t=3550 and fulfillment at t=3700: needs 600ms, only 150ms elapsed."""
        graph, timeline, gt = load_trace("gamma")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("gamma_e05", "gamma_e07")
        assert result is not None
        assert result.classification == "independent", (
            f"Expected gamma_e05->gamma_e07 to be independent, got {result.classification}"
        )

    def test_gamma_timing_independent_fulfillment_to_email(self):
        """Fulfillment at t=3700 and email at t=3800: needs 450ms, only 100ms elapsed."""
        graph, timeline, gt = load_trace("gamma")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("gamma_e07", "gamma_e08")
        assert result is not None
        assert result.classification == "independent", (
            f"Expected gamma_e07->gamma_e08 to be independent, got {result.classification}"
        )

    def test_gamma_burst_all_independent(self):
        """Load balancer at t=7000 and all services at t=7020-7060 are independent (timing too tight)."""
        graph, timeline, gt = load_trace("gamma")
        engine, results = run_correlation(graph, timeline)

        # LB to pricing: path lb->web->catalog->pricing needs 100+300+400=800ms, only 20ms elapsed
        result = engine.get_result("gamma_e09", "gamma_e10")
        assert result is not None
        assert result.classification == "independent", (
            f"Expected gamma_e09->gamma_e10 to be independent, got {result.classification}"
        )

    def test_gamma_burst_lb_to_fulfillment_independent(self):
        """LB to fulfillment: path needs 100+350+600=1050ms, only 40ms elapsed."""
        graph, timeline, gt = load_trace("gamma")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("gamma_e09", "gamma_e11")
        assert result is not None
        assert result.classification == "independent", (
            f"Expected gamma_e09->gamma_e11 to be independent, got {result.classification}"
        )

    def test_gamma_frontend_to_catalog_independent(self):
        """Frontend at t=7030 and catalog at t=7050: needs 300ms, only 20ms elapsed."""
        graph, timeline, gt = load_trace("gamma")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("gamma_e13", "gamma_e14")
        assert result is not None
        assert result.classification == "independent", (
            f"Expected gamma_e13->gamma_e14 to be independent, got {result.classification}"
        )


# === DELTA TRACE TESTS ===

class TestDeltaTraceClassification:
    """Test correct classification of event pairs in trace_delta."""

    def test_delta_ingress_to_auth_causal(self):
        """Ingress at t=1500 should cause auth_proxy at t=1700 (delay=150ms, elapsed=200ms)."""
        graph, timeline, gt = load_trace("delta")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("delta_e01", "delta_e02")
        assert result is not None
        assert result.classification == "causal", (
            f"Expected delta_e01->delta_e02 to be causal, got {result.classification}"
        )

    def test_delta_timing_independent_ingress_to_billing(self):
        """Ingress at t=6000 to billing at t=6030: path needs 150+300=450ms, only 30ms elapsed."""
        graph, timeline, gt = load_trace("delta")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("delta_e09", "delta_e10")
        assert result is not None
        assert result.classification == "independent", (
            f"Expected delta_e09->delta_e10 to be independent, got {result.classification}"
        )

    def test_delta_timing_independent_ingress_to_subscription(self):
        """Ingress at t=6000 to subscription at t=6020: path needs 150+250=400ms, only 20ms elapsed."""
        graph, timeline, gt = load_trace("delta")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("delta_e09", "delta_e11")
        assert result is not None
        assert result.classification == "independent", (
            f"Expected delta_e09->delta_e11 to be independent, got {result.classification}"
        )

    def test_delta_timing_independent_ingress_to_usage(self):
        """Ingress at t=6000 to usage at t=6050: path needs 150+300+400=850ms, only 50ms elapsed."""
        graph, timeline, gt = load_trace("delta")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("delta_e09", "delta_e12")
        assert result is not None
        assert result.classification == "independent", (
            f"Expected delta_e09->delta_e12 to be independent, got {result.classification}"
        )

    def test_delta_timing_independent_auth_to_billing(self):
        """Auth at t=6010 to billing at t=6030: path needs 300ms, only 20ms elapsed."""
        graph, timeline, gt = load_trace("delta")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("delta_e16", "delta_e10")
        assert result is not None
        assert result.classification == "independent", (
            f"Expected delta_e16->delta_e10 to be independent, got {result.classification}"
        )

    def test_delta_ingress_to_webhook_independent(self):
        """Ingress at t=9500 to webhook at t=9530: path too long for 30ms elapsed."""
        graph, timeline, gt = load_trace("delta")
        engine, results = run_correlation(graph, timeline)
        result = engine.get_result("delta_e17", "delta_e18")
        assert result is not None
        assert result.classification == "independent", (
            f"Expected delta_e17->delta_e18 to be independent, got {result.classification}"
        )


# === METRICS TESTS ===

class TestMetricsAccuracy:
    """Test that the correlation engine achieves acceptable accuracy metrics."""

    def test_alpha_precision_minimum(self):
        """Alpha trace should achieve precision >= 0.80."""
        graph, timeline, gt = load_trace("alpha")
        _, results = run_correlation(graph, timeline)
        metrics = quick_evaluate(results, gt)
        assert metrics["precision"] >= 0.80, (
            f"Alpha precision {metrics['precision']:.4f} below threshold 0.80"
        )

    def test_beta_precision_minimum(self):
        """Beta trace should achieve precision >= 0.75."""
        graph, timeline, gt = load_trace("beta")
        _, results = run_correlation(graph, timeline)
        metrics = quick_evaluate(results, gt)
        assert metrics["precision"] >= 0.75, (
            f"Beta precision {metrics['precision']:.4f} below threshold 0.75"
        )

    def test_gamma_precision_minimum(self):
        """Gamma trace should achieve precision >= 0.75."""
        graph, timeline, gt = load_trace("gamma")
        _, results = run_correlation(graph, timeline)
        metrics = quick_evaluate(results, gt)
        assert metrics["precision"] >= 0.75, (
            f"Gamma precision {metrics['precision']:.4f} below threshold 0.75"
        )

    def test_delta_precision_minimum(self):
        """Delta trace should achieve precision >= 0.80."""
        graph, timeline, gt = load_trace("delta")
        _, results = run_correlation(graph, timeline)
        metrics = quick_evaluate(results, gt)
        assert metrics["precision"] >= 0.80, (
            f"Delta precision {metrics['precision']:.4f} below threshold 0.80"
        )

    def test_overall_f1_minimum(self):
        """Average F1 across all traces should be >= 0.78."""
        f1_scores = []
        for name in ["alpha", "beta", "gamma", "delta"]:
            graph, timeline, gt = load_trace(name)
            _, results = run_correlation(graph, timeline)
            metrics = quick_evaluate(results, gt)
            f1_scores.append(metrics["f1_score"])
        avg_f1 = sum(f1_scores) / len(f1_scores)
        assert avg_f1 >= 0.78, (
            f"Average F1 {avg_f1:.4f} below threshold 0.78"
        )


# === AGGREGATION TESTS ===

class TestAggregation:
    """Test aggregation report correctness."""

    def test_alpha_causal_chain_detection(self):
        """Alpha trace should detect at least 2 causal chains."""
        graph, timeline, gt = load_trace("alpha")
        engine, results = run_correlation(graph, timeline)
        aggregator = CorrelationAggregator(graph, timeline)
        report = aggregator.aggregate(results)
        assert report.causal_pairs >= 4, (
            f"Expected at least 4 causal pairs in alpha, got {report.causal_pairs}"
        )

    def test_delta_independent_count(self):
        """Delta trace burst events should produce many independent classifications."""
        graph, timeline, gt = load_trace("delta")
        engine, results = run_correlation(graph, timeline)
        aggregator = CorrelationAggregator(graph, timeline)
        report = aggregator.aggregate(results)
        assert report.independent_pairs >= 10, (
            f"Expected at least 10 independent pairs in delta, got {report.independent_pairs}"
        )
