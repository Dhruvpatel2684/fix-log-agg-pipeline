"""
Correlation Aggregator Module
==============================
Aggregates correlation results into structured reports grouped by service,
severity, time window, and causal chain. Produces summary statistics and
formatted output for downstream consumption.
"""

from __future__ import annotations
import json
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .correlator import CorrelationResult, CLASSIFICATION_CAUSAL, CLASSIFICATION_INDEPENDENT
from .events import AnomalyEvent, EventTimeline
from .graph import ServiceDependencyGraph


@dataclass
class CausalChain:
    """Represents a chain of causally related events."""
    chain_id: str
    root_event_id: str
    root_service: str
    events: List[str] = field(default_factory=list)
    services: List[str] = field(default_factory=list)
    total_propagation_ms: float = 0.0
    severity_max: str = "low"

    def length(self) -> int:
        return len(self.events)


@dataclass
class ServiceSummary:
    """Summary of correlation results for a single service."""
    service_id: str
    total_events: int = 0
    causal_as_source: int = 0
    causal_as_target: int = 0
    independent_count: int = 0
    avg_confidence: float = 0.0
    chains_initiated: int = 0


@dataclass
class AggregationReport:
    """Complete aggregation report."""
    total_pairs: int = 0
    causal_pairs: int = 0
    independent_pairs: int = 0
    uncertain_pairs: int = 0
    causal_chains: List[CausalChain] = field(default_factory=list)
    service_summaries: Dict[str, ServiceSummary] = field(default_factory=dict)
    time_window_ms: int = 0
    avg_confidence: float = 0.0
    max_chain_length: int = 0
    coverage_ratio: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "total_pairs": self.total_pairs,
            "causal_pairs": self.causal_pairs,
            "independent_pairs": self.independent_pairs,
            "uncertain_pairs": self.uncertain_pairs,
            "causal_chain_count": len(self.causal_chains),
            "max_chain_length": self.max_chain_length,
            "avg_confidence": round(self.avg_confidence, 4),
            "coverage_ratio": round(self.coverage_ratio, 4),
            "service_summaries": {
                k: {
                    "total_events": v.total_events,
                    "causal_as_source": v.causal_as_source,
                    "causal_as_target": v.causal_as_target,
                    "independent_count": v.independent_count,
                }
                for k, v in self.service_summaries.items()
            },
        }


class CorrelationAggregator:
    """
    Aggregates raw correlation results into structured reports with
    causal chain detection and service-level summaries.
    """

    def __init__(
        self,
        graph: ServiceDependencyGraph,
        timeline: EventTimeline,
    ):
        self._graph = graph
        self._timeline = timeline
        self._event_map: Dict[str, AnomalyEvent] = {}
        for event in timeline.get_all():
            self._event_map[event.event_id] = event

    def aggregate(self, results: List[CorrelationResult]) -> AggregationReport:
        """
        Build a complete aggregation report from correlation results.
        """
        report = AggregationReport()
        report.total_pairs = len(results)
        report.time_window_ms = self._timeline.time_span_ms()

        # Count classifications
        causal_results = []
        for result in results:
            if result.classification == CLASSIFICATION_CAUSAL:
                report.causal_pairs += 1
                causal_results.append(result)
            elif result.classification == CLASSIFICATION_INDEPENDENT:
                report.independent_pairs += 1
            else:
                report.uncertain_pairs += 1

        # Compute average confidence
        if results:
            report.avg_confidence = sum(r.confidence for r in results) / len(results)

        # Build service summaries
        report.service_summaries = self._build_service_summaries(results)

        # Detect causal chains
        report.causal_chains = self._detect_causal_chains(causal_results)
        if report.causal_chains:
            report.max_chain_length = max(c.length() for c in report.causal_chains)

        # Coverage ratio
        all_services = set(self._graph.get_services())
        affected_services = set()
        for event in self._timeline.get_all():
            affected_services.add(event.service_id)
        if all_services:
            report.coverage_ratio = len(affected_services & all_services) / len(all_services)

        return report

    def _build_service_summaries(
        self, results: List[CorrelationResult]
    ) -> Dict[str, ServiceSummary]:
        """Build per-service summary statistics."""
        summaries: Dict[str, ServiceSummary] = {}

        # Initialize from timeline
        service_events = self._timeline.group_by_service()
        for service_id, events in service_events.items():
            summaries[service_id] = ServiceSummary(
                service_id=service_id,
                total_events=len(events),
            )

        # Accumulate from results
        confidence_sums: Dict[str, Tuple[float, int]] = defaultdict(lambda: (0.0, 0))
        for result in results:
            event_a = self._event_map.get(result.event_a_id)
            event_b = self._event_map.get(result.event_b_id)
            if not event_a or not event_b:
                continue

            svc_a = event_a.service_id
            svc_b = event_b.service_id

            if svc_a not in summaries:
                summaries[svc_a] = ServiceSummary(service_id=svc_a)
            if svc_b not in summaries:
                summaries[svc_b] = ServiceSummary(service_id=svc_b)

            if result.classification == CLASSIFICATION_CAUSAL:
                summaries[svc_a].causal_as_source += 1
                summaries[svc_b].causal_as_target += 1
            elif result.classification == CLASSIFICATION_INDEPENDENT:
                summaries[svc_a].independent_count += 1
                summaries[svc_b].independent_count += 1

        return summaries

    def _detect_causal_chains(
        self, causal_results: List[CorrelationResult]
    ) -> List[CausalChain]:
        """
        Detect causal chains by finding connected components in the causal
        relationship graph. Each chain represents a cascade of failures.
        """
        if not causal_results:
            return []

        # Build adjacency from causal pairs
        adjacency: Dict[str, Set[str]] = defaultdict(set)
        for result in causal_results:
            adjacency[result.event_a_id].add(result.event_b_id)
            adjacency[result.event_b_id].add(result.event_a_id)

        # Find connected components via BFS
        visited: Set[str] = set()
        chains: List[CausalChain] = []
        chain_counter = 0

        all_events = set()
        for result in causal_results:
            all_events.add(result.event_a_id)
            all_events.add(result.event_b_id)

        for start_event in sorted(all_events):
            if start_event in visited:
                continue

            chain_counter += 1
            component: List[str] = []
            queue = [start_event]
            visited.add(start_event)

            while queue:
                current = queue.pop(0)
                component.append(current)
                for neighbor in adjacency.get(current, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)

            # Sort by timestamp
            component_events = [
                self._event_map[eid]
                for eid in component
                if eid in self._event_map
            ]
            component_events.sort(key=lambda e: e.timestamp_ms)

            if component_events:
                root = component_events[0]
                services = list(dict.fromkeys(e.service_id for e in component_events))
                chain = CausalChain(
                    chain_id=f"chain_{chain_counter:03d}",
                    root_event_id=root.event_id,
                    root_service=root.service_id,
                    events=[e.event_id for e in component_events],
                    services=services,
                    total_propagation_ms=(
                        component_events[-1].timestamp_ms - component_events[0].timestamp_ms
                    ),
                    severity_max=max(
                        (e.severity.value for e in component_events),
                        key=lambda s: {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}.get(s, 0),
                    ),
                )
                chains.append(chain)

        return chains

    def format_report_json(self, report: AggregationReport) -> str:
        """Format report as JSON string."""
        return json.dumps(report.to_dict(), indent=2)

    def get_root_cause_candidates(
        self, results: List[CorrelationResult]
    ) -> List[Tuple[str, int]]:
        """
        Identify likely root cause services based on causal chain analysis.
        Returns list of (service_id, outgoing_causal_count) sorted descending.
        """
        outgoing: Dict[str, int] = defaultdict(int)
        incoming: Dict[str, int] = defaultdict(int)

        for result in results:
            if result.classification != CLASSIFICATION_CAUSAL:
                continue
            event_a = self._event_map.get(result.event_a_id)
            event_b = self._event_map.get(result.event_b_id)
            if event_a and event_b:
                if event_a.timestamp_ms <= event_b.timestamp_ms:
                    outgoing[event_a.service_id] += 1
                    incoming[event_b.service_id] += 1
                else:
                    outgoing[event_b.service_id] += 1
                    incoming[event_a.service_id] += 1

        # Root causes have high outgoing and low incoming
        candidates = []
        for svc, out_count in outgoing.items():
            in_count = incoming.get(svc, 0)
            if out_count > in_count:
                candidates.append((svc, out_count))

        candidates.sort(key=lambda x: -x[1])
        return candidates

    def compute_impact_radius(self, results: List[CorrelationResult]) -> Dict[str, int]:
        """
        For each service, compute how many other services are affected
        through causal relationships originating from it.
        """
        impact: Dict[str, Set[str]] = defaultdict(set)

        for result in results:
            if result.classification != CLASSIFICATION_CAUSAL:
                continue
            event_a = self._event_map.get(result.event_a_id)
            event_b = self._event_map.get(result.event_b_id)
            if event_a and event_b:
                if event_a.timestamp_ms <= event_b.timestamp_ms:
                    impact[event_a.service_id].add(event_b.service_id)
                else:
                    impact[event_b.service_id].add(event_a.service_id)

        return {svc: len(targets) for svc, targets in impact.items()}
