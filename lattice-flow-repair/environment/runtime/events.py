"""
Anomaly Event Module
=====================
Handles parsing, validation, and manipulation of anomaly events from the
distributed monitoring system. Each event represents a detected anomaly
at a specific service with a timestamp and severity metadata.

Events are ordered by timestamp and can be grouped by service, severity,
or temporal window for batch processing.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class Severity(Enum):
    """Anomaly severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @classmethod
    def from_string(cls, value: str) -> "Severity":
        normalized = value.strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        return cls.MEDIUM

    def numeric_weight(self) -> float:
        weights = {
            Severity.CRITICAL: 1.0,
            Severity.HIGH: 0.8,
            Severity.MEDIUM: 0.6,
            Severity.LOW: 0.4,
            Severity.INFO: 0.2,
        }
        return weights[self]


@dataclass(frozen=True)
class AnomalyEvent:
    """
    A single anomaly detection event from the monitoring system.

    Attributes:
        event_id: Unique identifier for this event
        service_id: The service where the anomaly was detected
        timestamp_ms: Detection timestamp in epoch milliseconds
        severity: Severity classification of the anomaly
        metric_name: The metric that triggered the anomaly
        metric_value: The observed anomalous value
        baseline_value: The expected baseline value
        deviation_sigma: Number of standard deviations from baseline
        labels: Additional metadata labels
    """
    event_id: str
    service_id: str
    timestamp_ms: int
    severity: Severity = Severity.MEDIUM
    metric_name: str = ""
    metric_value: float = 0.0
    baseline_value: float = 0.0
    deviation_sigma: float = 0.0
    labels: Dict[str, str] = field(default_factory=dict)

    def time_delta_ms(self, other: "AnomalyEvent") -> int:
        """Absolute time difference in milliseconds between two events."""
        return abs(self.timestamp_ms - other.timestamp_ms)

    def is_before(self, other: "AnomalyEvent") -> bool:
        """Check if this event occurred before another."""
        return self.timestamp_ms < other.timestamp_ms

    def is_after(self, other: "AnomalyEvent") -> bool:
        """Check if this event occurred after another."""
        return self.timestamp_ms > other.timestamp_ms

    def severity_weight(self) -> float:
        """Numeric weight based on severity."""
        return self.severity.numeric_weight()

    def to_dict(self) -> Dict:
        return {
            "event_id": self.event_id,
            "service_id": self.service_id,
            "timestamp_ms": self.timestamp_ms,
            "severity": self.severity.value,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "baseline_value": self.baseline_value,
            "deviation_sigma": self.deviation_sigma,
            "labels": self.labels,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "AnomalyEvent":
        return cls(
            event_id=data["event_id"],
            service_id=data["service_id"],
            timestamp_ms=int(data["timestamp_ms"]),
            severity=Severity.from_string(data.get("severity", "medium")),
            metric_name=data.get("metric_name", ""),
            metric_value=float(data.get("metric_value", 0.0)),
            baseline_value=float(data.get("baseline_value", 0.0)),
            deviation_sigma=float(data.get("deviation_sigma", 0.0)),
            labels=data.get("labels", {}),
        )


class EventTimeline:
    """
    Ordered collection of anomaly events supporting temporal queries.
    Events are maintained in timestamp order for efficient windowed access.
    """

    def __init__(self, events: Optional[List[AnomalyEvent]] = None):
        self._events: List[AnomalyEvent] = []
        if events:
            for e in events:
                self.add(e)

    def add(self, event: AnomalyEvent) -> None:
        """Insert event maintaining timestamp order."""
        lo, hi = 0, len(self._events)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._events[mid].timestamp_ms <= event.timestamp_ms:
                lo = mid + 1
            else:
                hi = mid
        self._events.insert(lo, event)

    def get_all(self) -> List[AnomalyEvent]:
        """Return all events in timestamp order."""
        return list(self._events)

    def get_by_service(self, service_id: str) -> List[AnomalyEvent]:
        """Return events for a specific service."""
        return [e for e in self._events if e.service_id == service_id]

    def get_in_window(self, start_ms: int, end_ms: int) -> List[AnomalyEvent]:
        """Return events within a time window [start_ms, end_ms]."""
        return [
            e for e in self._events
            if start_ms <= e.timestamp_ms <= end_ms
        ]

    def get_pairs_in_window(
        self, window_ms: int
    ) -> List[Tuple[AnomalyEvent, AnomalyEvent]]:
        """
        Generate all event pairs (a, b) where a occurs before b
        and b.timestamp - a.timestamp <= window_ms.
        """
        pairs = []
        n = len(self._events)
        for i in range(n):
            for j in range(i + 1, n):
                delta = self._events[j].timestamp_ms - self._events[i].timestamp_ms
                if delta > window_ms:
                    break
                pairs.append((self._events[i], self._events[j]))
        return pairs

    def get_by_severity(self, min_severity: Severity) -> List[AnomalyEvent]:
        """Return events at or above a minimum severity level."""
        threshold = min_severity.numeric_weight()
        return [e for e in self._events if e.severity_weight() >= threshold]

    def group_by_service(self) -> Dict[str, List[AnomalyEvent]]:
        """Group events by service ID."""
        groups: Dict[str, List[AnomalyEvent]] = {}
        for e in self._events:
            if e.service_id not in groups:
                groups[e.service_id] = []
            groups[e.service_id].append(e)
        return groups

    def count(self) -> int:
        return len(self._events)

    def time_span_ms(self) -> int:
        """Total time span from first to last event."""
        if len(self._events) < 2:
            return 0
        return self._events[-1].timestamp_ms - self._events[0].timestamp_ms

    def earliest(self) -> Optional[AnomalyEvent]:
        return self._events[0] if self._events else None

    def latest(self) -> Optional[AnomalyEvent]:
        return self._events[-1] if self._events else None


class GroundTruthLabels:
    """
    Stores ground truth causal relationship labels for event pairs.
    Used for evaluation of the correlation engine's accuracy.
    """

    def __init__(self):
        self._labels: Dict[Tuple[str, str], str] = {}

    def add_label(self, event_a_id: str, event_b_id: str, relationship: str) -> None:
        """
        Add a ground truth label.
        relationship should be one of: 'causal', 'independent', 'uncertain'
        """
        key = self._normalize_key(event_a_id, event_b_id)
        self._labels[key] = relationship

    def get_label(self, event_a_id: str, event_b_id: str) -> Optional[str]:
        """Get the ground truth label for an event pair."""
        key = self._normalize_key(event_a_id, event_b_id)
        return self._labels.get(key)

    def get_all_causal(self) -> List[Tuple[str, str]]:
        """Return all event pairs labeled as causally related."""
        return [k for k, v in self._labels.items() if v == "causal"]

    def get_all_independent(self) -> List[Tuple[str, str]]:
        """Return all event pairs labeled as independent."""
        return [k for k, v in self._labels.items() if v == "independent"]

    def total_labeled(self) -> int:
        return len(self._labels)

    def causal_count(self) -> int:
        return sum(1 for v in self._labels.values() if v == "causal")

    def independent_count(self) -> int:
        return sum(1 for v in self._labels.values() if v == "independent")

    @staticmethod
    def _normalize_key(a: str, b: str) -> Tuple[str, str]:
        """Normalize pair key so (a,b) and (b,a) map to the same entry."""
        return (min(a, b), max(a, b))

    @classmethod
    def from_list(cls, labels: List[Dict]) -> "GroundTruthLabels":
        """
        Build from list of dicts:
        [{"event_a": "e1", "event_b": "e2", "relationship": "causal"}, ...]
        """
        gt = cls()
        for item in labels:
            gt.add_label(item["event_a"], item["event_b"], item["relationship"])
        return gt


def load_events_from_json(filepath: str) -> Tuple[EventTimeline, "GroundTruthLabels"]:
    """
    Load events and ground truth from a JSON trace file.
    Expected format:
    {
        "graph": {...},
        "events": [...],
        "ground_truth": [...]
    }
    """
    with open(filepath, "r") as f:
        data = json.load(f)

    timeline = EventTimeline()
    for event_data in data.get("events", []):
        event = AnomalyEvent.from_dict(event_data)
        timeline.add(event)

    labels = GroundTruthLabels.from_list(data.get("ground_truth", []))
    return timeline, labels


def parse_event_batch(raw_events: List[Dict]) -> List[AnomalyEvent]:
    """Parse a batch of raw event dictionaries into AnomalyEvent objects."""
    events = []
    for raw in raw_events:
        try:
            event = AnomalyEvent.from_dict(raw)
            events.append(event)
        except (KeyError, ValueError):
            continue
    return events


def compute_inter_event_gaps(events: List[AnomalyEvent]) -> List[int]:
    """Compute time gaps between consecutive events in milliseconds."""
    if len(events) < 2:
        return []
    sorted_events = sorted(events, key=lambda e: e.timestamp_ms)
    return [
        sorted_events[i + 1].timestamp_ms - sorted_events[i].timestamp_ms
        for i in range(len(sorted_events) - 1)
    ]


def filter_events_by_deviation(
    events: List[AnomalyEvent], min_sigma: float = 2.0
) -> List[AnomalyEvent]:
    """Filter events to only include those with deviation >= min_sigma."""
    return [e for e in events if e.deviation_sigma >= min_sigma]
