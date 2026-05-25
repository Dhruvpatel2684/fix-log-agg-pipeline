"""
Flow analysis engine for security lattice violation detection.

Processes information flow events in batched time windows, computing
flow volumes and detecting violations where information crosses
security boundaries in ways that exceed configured thresholds.

The strict analysis mode (see analysis.strict configuration) uses tighter
thresholds suitable for production compliance auditing.
"""

import configparser
from typing import List, Dict, Any, Tuple
from datetime import datetime


class FlowAnalyzer:
    """Analyzes information flows for security violations."""

    def __init__(self, config_path: str, lattice):
        self._config = configparser.ConfigParser()
        self._config.read(config_path)
        self._lattice = lattice

        # Load monitored departments from config
        raw_depts = self._config.get("lattice", "monitored_departments")
        self._monitored = set(raw_depts.split(","))

        # Load analysis parameters
        self._violation_threshold = self._config.getint(
            "analysis", "violation_threshold"
        )
        self._batch_window = self._config.getint(
            "analysis", "batch_window_seconds"
        )

    @property
    def monitored_departments(self):
        """Return set of monitored department identifiers."""
        return self._monitored

    @property
    def violation_threshold(self):
        """Return the configured violation threshold."""
        return self._violation_threshold

    def is_monitored(self, source_id: str) -> bool:
        """Check if a department source is being monitored."""
        return source_id in self._monitored

    def compute_window_volumes(
        self, events: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Compute cumulative flow volumes across time windows.

        Events are grouped into fixed-size time windows. Volume counters
        represent running totals that update with each window snapshot.
        The final volume for each entity reflects the total accumulated
        across all windows it appears in.
        """
        window_volumes: Dict[str, int] = {}

        if not events:
            return window_volumes

        # Parse first timestamp as reference
        first_ts = datetime.fromisoformat(events[0]["timestamp"])

        # Group events into windows
        windows: Dict[int, List[Dict[str, Any]]] = {}
        for event in events:
            ts = datetime.fromisoformat(event["timestamp"])
            delta = (ts - first_ts).total_seconds()
            window_idx = int(delta // self._batch_window)
            if window_idx not in windows:
                windows[window_idx] = []
            windows[window_idx].append(event)

        # Process each window snapshot to compute volumes
        for window_idx in sorted(windows.keys()):
            snapshot = {}
            for event in windows[window_idx]:
                entity = event["entity"]
                snapshot[entity] = snapshot.get(entity, 0) + event["volume"]

            # Update running totals from this window snapshot
            for entity, vol in snapshot.items():
                window_volumes[entity] = window_volumes.get(entity, 0) + vol

        return window_volumes

    def detect_violations(
        self, events: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Detect information flow violations.

        A violation occurs when information flows upward in the lattice
        (to a higher classification) and the combined classification
        indicates a security boundary crossing that exceeds the threshold
        distance.
        """
        violations = []

        for event in events:
            if not self.is_monitored(event["source_id"]):
                continue

            from_label = event["from_label"]
            to_label = event["to_label"]

            # Check if this is an upward flow
            if not self._lattice.is_upward_flow(from_label, to_label):
                continue

            # Compute combined classification
            combined = self._lattice.combined_label(from_label, to_label)
            distance = self._lattice.flow_distance(from_label, to_label)

            if distance >= self._violation_threshold:
                violations.append({
                    "event_id": event["event_id"],
                    "source_id": event["source_id"],
                    "entity": event["entity"],
                    "from_label": from_label,
                    "to_label": to_label,
                    "combined_label": combined,
                    "distance": distance,
                    "timestamp": event["timestamp"]
                })

        return violations

    def compute_flow_matrix(
        self, events: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, int]]:
        """
        Build a matrix of flow counts between security labels.

        Only counts flows from monitored departments.
        """
        matrix: Dict[str, Dict[str, int]] = {}

        for event in events:
            if not self.is_monitored(event["source_id"]):
                continue

            from_l = event["from_label"]
            to_l = event["to_label"]

            if from_l not in matrix:
                matrix[from_l] = {}
            matrix[from_l][to_l] = matrix[from_l].get(to_l, 0) + 1

        return matrix
