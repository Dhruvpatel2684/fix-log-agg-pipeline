"""
Anomaly Correlation Engine
============================
Core correlation module that determines causal relationships between anomaly
events across a service dependency graph. Uses structural graph analysis to
identify which anomalies are causally linked through service dependencies
versus coincidental co-occurrences.

The engine processes event pairs within a configurable time window and
classifies each pair as either 'causal' (one event caused the other through
dependency propagation) or 'independent' (no causal relationship exists).
"""

from __future__ import annotations
import math
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from .graph import ServiceDependencyGraph
from .events import AnomalyEvent, EventTimeline, Severity


# Classification constants
CLASSIFICATION_CAUSAL = "causal"
CLASSIFICATION_INDEPENDENT = "independent"
CLASSIFICATION_UNCERTAIN = "uncertain"

# Default configuration
DEFAULT_WINDOW_MS = 30000
DEFAULT_CONFIDENCE_THRESHOLD = 0.6
DEFAULT_MAX_HOPS = 8


class CorrelationResult:
    """Result of correlating a pair of events."""

    __slots__ = (
        "event_a_id",
        "event_b_id",
        "classification",
        "confidence",
        "path",
        "propagation_delay_ms",
        "reasoning",
    )

    def __init__(
        self,
        event_a_id: str,
        event_b_id: str,
        classification: str,
        confidence: float = 0.0,
        path: Optional[List[str]] = None,
        propagation_delay_ms: float = 0.0,
        reasoning: str = "",
    ):
        self.event_a_id = event_a_id
        self.event_b_id = event_b_id
        self.classification = classification
        self.confidence = confidence
        self.path = path or []
        self.propagation_delay_ms = propagation_delay_ms
        self.reasoning = reasoning

    def is_causal(self) -> bool:
        return self.classification == CLASSIFICATION_CAUSAL

    def is_independent(self) -> bool:
        return self.classification == CLASSIFICATION_INDEPENDENT

    def to_dict(self) -> Dict:
        return {
            "event_a_id": self.event_a_id,
            "event_b_id": self.event_b_id,
            "classification": self.classification,
            "confidence": self.confidence,
            "path": self.path,
            "propagation_delay_ms": self.propagation_delay_ms,
            "reasoning": self.reasoning,
        }


class CorrelationEngine:
    """
    Main correlation engine that processes anomaly events against a service
    dependency graph to determine causal relationships.

    The engine uses multiple heuristics including graph reachability,
    temporal proximity, severity correlation, and metric similarity to
    produce a final classification for each event pair.
    """

    def __init__(
        self,
        graph: ServiceDependencyGraph,
        window_ms: int = DEFAULT_WINDOW_MS,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        max_hops: int = DEFAULT_MAX_HOPS,
    ):
        self._graph = graph
        self._window_ms = window_ms
        self._confidence_threshold = confidence_threshold
        self._max_hops = max_hops
        self._results: List[CorrelationResult] = []
        self._pair_cache: Dict[Tuple[str, str], CorrelationResult] = {}

    @property
    def results(self) -> List[CorrelationResult]:
        return list(self._results)

    @property
    def graph(self) -> ServiceDependencyGraph:
        return self._graph

    def correlate_events(
        self, timeline: EventTimeline
    ) -> List[CorrelationResult]:
        """
        Process all event pairs within the correlation window and classify
        their causal relationship.
        """
        self._results.clear()
        self._pair_cache.clear()

        events = timeline.get_all()
        n = len(events)

        for i in range(n):
            for j in range(i + 1, n):
                event_a = events[i]
                event_b = events[j]

                time_delta = event_b.timestamp_ms - event_a.timestamp_ms
                if time_delta > self._window_ms:
                    break

                result = self._classify_pair(event_a, event_b)
                self._results.append(result)
                cache_key = self._make_cache_key(event_a.event_id, event_b.event_id)
                self._pair_cache[cache_key] = result

        return self._results

    def get_result(
        self, event_a_id: str, event_b_id: str
    ) -> Optional[CorrelationResult]:
        """Retrieve cached result for a specific event pair."""
        key = self._make_cache_key(event_a_id, event_b_id)
        return self._pair_cache.get(key)

    def get_causal_pairs(self) -> List[CorrelationResult]:
        """Return all pairs classified as causally related."""
        return [r for r in self._results if r.is_causal()]

    def get_independent_pairs(self) -> List[CorrelationResult]:
        """Return all pairs classified as independent."""
        return [r for r in self._results if r.is_independent()]

    def _classify_pair(
        self, event_a: AnomalyEvent, event_b: AnomalyEvent
    ) -> CorrelationResult:
        """
        Classify a pair of events as causal or independent based on
        multiple analysis dimensions.
        """
        # Compute individual scores from different dimensions
        structural_score = self._compute_structural_score(event_a, event_b)
        temporal_score = self._compute_temporal_score(event_a, event_b)
        severity_score = self._compute_severity_score(event_a, event_b)
        metric_score = self._compute_metric_similarity(event_a, event_b)

        # Check causal independence (the primary structural filter)
        if self._check_independence(event_a, event_b):
            return CorrelationResult(
                event_a_id=event_a.event_id,
                event_b_id=event_b.event_id,
                classification=CLASSIFICATION_INDEPENDENT,
                confidence=0.9,
                reasoning="Events are causally independent in dependency graph",
            )

        # Weighted combination of scores
        weights = self._get_dimension_weights(event_a, event_b)
        combined_score = (
            weights["structural"] * structural_score
            + weights["temporal"] * temporal_score
            + weights["severity"] * severity_score
            + weights["metric"] * metric_score
        )

        # Normalize
        total_weight = sum(weights.values())
        if total_weight > 0:
            combined_score /= total_weight

        # Apply confidence threshold
        if combined_score >= self._confidence_threshold:
            path = self._find_causal_path(event_a, event_b)
            delay = self._estimate_propagation_delay(event_a, event_b)
            return CorrelationResult(
                event_a_id=event_a.event_id,
                event_b_id=event_b.event_id,
                classification=CLASSIFICATION_CAUSAL,
                confidence=combined_score,
                path=path,
                propagation_delay_ms=delay,
                reasoning="Events are causally related through service dependencies",
            )
        else:
            return CorrelationResult(
                event_a_id=event_a.event_id,
                event_b_id=event_b.event_id,
                classification=CLASSIFICATION_INDEPENDENT,
                confidence=1.0 - combined_score,
                reasoning="Correlation score below confidence threshold",
            )

    def _check_independence(
        self, event_a: AnomalyEvent, event_b: AnomalyEvent
    ) -> bool:
        """
        Determine if two events are causally independent based on the
        service dependency graph structure.

        Two events are considered causally independent if there is no directed
        path in the dependency graph connecting their respective services in
        either direction. This means neither service can influence the other
        through the dependency chain, making any temporal correlation purely
        coincidental.

        Args:
            event_a: First anomaly event
            event_b: Second anomaly event

        Returns:
            True if the events are causally independent (no dependency path),
            False if a potential causal relationship exists.
        """
        source_service = event_a.service_id
        target_service = event_b.service_id

        if source_service == target_service:
            return False

        # Check if there is any directed path between the two services
        forward_reachable = self._graph.is_reachable(source_service, target_service)
        backward_reachable = self._graph.is_reachable(target_service, source_service)

        # Independent if neither service can reach the other
        return not forward_reachable and not backward_reachable

    def _compute_structural_score(
        self, event_a: AnomalyEvent, event_b: AnomalyEvent
    ) -> float:
        """
        Compute structural correlation score based on graph distance.
        Closer services in the dependency graph get higher scores.
        """
        path = self._graph.shortest_path(event_a.service_id, event_b.service_id)
        if path is None:
            reverse_path = self._graph.shortest_path(
                event_b.service_id, event_a.service_id
            )
            if reverse_path is None:
                return 0.0
            path = reverse_path

        hop_count = len(path) - 1
        if hop_count == 0:
            return 1.0
        if hop_count > self._max_hops:
            return 0.0

        # Decay score with distance
        return 1.0 / (1.0 + math.log(hop_count + 1))

    def _compute_temporal_score(
        self, event_a: AnomalyEvent, event_b: AnomalyEvent
    ) -> float:
        """
        Compute temporal correlation score. Events closer in time get
        higher scores, with exponential decay.
        """
        delta_ms = abs(event_b.timestamp_ms - event_a.timestamp_ms)
        if delta_ms == 0:
            return 1.0

        # Exponential decay with half-life at window/4
        half_life = self._window_ms / 4.0
        decay = math.exp(-0.693 * delta_ms / half_life)
        return decay

    def _compute_severity_score(
        self, event_a: AnomalyEvent, event_b: AnomalyEvent
    ) -> float:
        """
        Compute severity correlation. Cascading failures tend to maintain
        or increase severity along the propagation path.
        """
        weight_a = event_a.severity_weight()
        weight_b = event_b.severity_weight()

        # Higher score if severity propagates (upstream high -> downstream high)
        if weight_a >= weight_b:
            return 0.5 + 0.5 * (weight_b / max(weight_a, 0.001))
        else:
            # Downstream more severe than upstream is less likely causal
            return 0.3 * (weight_a / max(weight_b, 0.001))

    def _compute_metric_similarity(
        self, event_a: AnomalyEvent, event_b: AnomalyEvent
    ) -> float:
        """
        Compute metric similarity score. Related anomalies often manifest
        in similar metric types (e.g., latency cascading to latency).
        """
        if not event_a.metric_name or not event_b.metric_name:
            return 0.5  # Neutral if metrics unknown

        if event_a.metric_name == event_b.metric_name:
            return 0.9

        # Check metric category similarity
        related_metrics = {
            "latency": {"response_time", "p99_latency", "p95_latency", "request_duration"},
            "errors": {"error_rate", "5xx_rate", "failure_count", "exception_rate"},
            "throughput": {"requests_per_second", "queue_depth", "connection_count"},
            "resources": {"cpu_usage", "memory_usage", "disk_io", "gc_pause"},
        }

        category_a = self._get_metric_category(event_a.metric_name, related_metrics)
        category_b = self._get_metric_category(event_b.metric_name, related_metrics)

        if category_a and category_b and category_a == category_b:
            return 0.7
        return 0.3

    def _get_metric_category(
        self, metric_name: str, categories: Dict[str, Set[str]]
    ) -> Optional[str]:
        """Find which category a metric belongs to."""
        for category, metrics in categories.items():
            if metric_name in metrics or metric_name == category:
                return category
        return None

    def _get_dimension_weights(
        self, event_a: AnomalyEvent, event_b: AnomalyEvent
    ) -> Dict[str, float]:
        """
        Get weights for each analysis dimension. Weights can be adjusted
        based on event characteristics.
        """
        weights = {
            "structural": 0.40,
            "temporal": 0.30,
            "severity": 0.15,
            "metric": 0.15,
        }

        # Boost structural weight for high-severity events
        if event_a.severity in (Severity.CRITICAL, Severity.HIGH):
            weights["structural"] = 0.50
            weights["temporal"] = 0.25
            weights["severity"] = 0.15
            weights["metric"] = 0.10

        return weights

    def _find_causal_path(
        self, event_a: AnomalyEvent, event_b: AnomalyEvent
    ) -> List[str]:
        """Find the most likely causal propagation path between two events."""
        forward = self._graph.shortest_path(event_a.service_id, event_b.service_id)
        if forward:
            return forward

        backward = self._graph.shortest_path(event_b.service_id, event_a.service_id)
        if backward:
            return backward

        return []

    def _estimate_propagation_delay(
        self, event_a: AnomalyEvent, event_b: AnomalyEvent
    ) -> float:
        """Estimate the expected propagation delay between two events."""
        delay = self._graph.minimum_propagation_delay(
            event_a.service_id, event_b.service_id
        )
        if delay is not None:
            return delay

        delay = self._graph.minimum_propagation_delay(
            event_b.service_id, event_a.service_id
        )
        return delay if delay is not None else 0.0

    def _compute_deviation_correlation(
        self, event_a: AnomalyEvent, event_b: AnomalyEvent
    ) -> float:
        """
        Compute correlation based on deviation magnitudes. Causal propagation
        typically shows attenuation of deviation along the path.
        """
        if event_a.deviation_sigma == 0 or event_b.deviation_sigma == 0:
            return 0.5

        ratio = min(event_a.deviation_sigma, event_b.deviation_sigma) / max(
            event_a.deviation_sigma, event_b.deviation_sigma
        )
        return ratio * 0.8

    def _check_transitive_relationship(
        self, event_a: AnomalyEvent, event_b: AnomalyEvent, all_events: List[AnomalyEvent]
    ) -> bool:
        """
        Check if two events might be related through a transitive chain
        of intermediate events.
        """
        for intermediate in all_events:
            if intermediate.event_id in (event_a.event_id, event_b.event_id):
                continue
            if (
                event_a.timestamp_ms <= intermediate.timestamp_ms <= event_b.timestamp_ms
                and self._graph.is_reachable(event_a.service_id, intermediate.service_id)
                and self._graph.is_reachable(intermediate.service_id, event_b.service_id)
            ):
                return True
        return False

    def _compute_topological_distance(
        self, event_a: AnomalyEvent, event_b: AnomalyEvent
    ) -> int:
        """
        Compute topological distance between two services in the DAG.
        Returns -1 if services are not in the same connected component.
        """
        topo_order = self._graph.topological_sort()
        if topo_order is None:
            return -1

        try:
            idx_a = topo_order.index(event_a.service_id)
            idx_b = topo_order.index(event_b.service_id)
            return abs(idx_b - idx_a)
        except ValueError:
            return -1

    def _apply_dampening(self, score: float, hop_count: int) -> float:
        """Apply signal dampening based on hop count in the dependency chain."""
        dampening_factor = 0.85
        return score * (dampening_factor ** hop_count)

    def _evaluate_path_coherence(self, path: List[str], timeline: EventTimeline) -> float:
        """
        Evaluate whether events along a path show temporal coherence
        (monotonically increasing timestamps along the path).
        """
        if len(path) < 2:
            return 1.0

        path_events = []
        for service in path:
            service_events = timeline.get_by_service(service)
            if service_events:
                path_events.append(service_events[0].timestamp_ms)
            else:
                path_events.append(None)

        # Check monotonicity
        valid_times = [t for t in path_events if t is not None]
        if len(valid_times) < 2:
            return 0.5

        monotonic_count = sum(
            1 for i in range(len(valid_times) - 1)
            if valid_times[i] <= valid_times[i + 1]
        )
        return monotonic_count / (len(valid_times) - 1)

    def _compute_fan_out_penalty(self, service_id: str) -> float:
        """
        Compute penalty for services with high fan-out (many downstream deps).
        High fan-out services are more likely to have coincidental correlations.
        """
        neighbors = self._graph.get_neighbors(service_id)
        fan_out = len(neighbors)
        if fan_out <= 2:
            return 1.0
        return 1.0 / math.log(fan_out + 1)

    def _compute_fan_in_boost(self, service_id: str) -> float:
        """
        Compute boost for services with high fan-in (many upstream deps).
        High fan-in services are more likely to be affected by upstream failures.
        """
        upstream = self._graph.get_upstream(service_id)
        fan_in = len(upstream)
        if fan_in <= 1:
            return 1.0
        return 1.0 + 0.1 * math.log(fan_in + 1)

    @staticmethod
    def _make_cache_key(event_a_id: str, event_b_id: str) -> Tuple[str, str]:
        """Normalize event pair key for caching."""
        return (min(event_a_id, event_b_id), max(event_a_id, event_b_id))


def correlate_trace(
    graph: ServiceDependencyGraph,
    timeline: EventTimeline,
    window_ms: int = DEFAULT_WINDOW_MS,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> List[CorrelationResult]:
    """
    Convenience function to correlate all events in a timeline against
    a service dependency graph.
    """
    engine = CorrelationEngine(
        graph=graph,
        window_ms=window_ms,
        confidence_threshold=confidence_threshold,
    )
    return engine.correlate_events(timeline)


def batch_correlate(
    graph: ServiceDependencyGraph,
    timelines: List[EventTimeline],
    window_ms: int = DEFAULT_WINDOW_MS,
) -> List[List[CorrelationResult]]:
    """Correlate multiple timelines in batch."""
    results = []
    for timeline in timelines:
        engine = CorrelationEngine(graph=graph, window_ms=window_ms)
        results.append(engine.correlate_events(timeline))
    return results


def compute_correlation_matrix(
    results: List[CorrelationResult], event_ids: List[str]
) -> Dict[Tuple[str, str], str]:
    """Build a correlation matrix from results."""
    matrix: Dict[Tuple[str, str], str] = {}
    for result in results:
        key = (
            min(result.event_a_id, result.event_b_id),
            max(result.event_a_id, result.event_b_id),
        )
        matrix[key] = result.classification
    return matrix
