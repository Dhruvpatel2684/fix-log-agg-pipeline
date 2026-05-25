"""
Flow analysis engine for product lattice violation detection.

Processes information flow events against a two-dimensional security
lattice (Confidentiality × Integrity), detecting cases where information
crosses classification boundaries in ways that constitute security
violations.

A flow is considered a violation when:
1. The destination dominates the source in the product lattice (upward flow)
2. The lattice distance exceeds the configured threshold
"""

import configparser
from typing import List, Dict, Any, Tuple


class FlowAnalyzer:
    """Analyzes information flows against a product security lattice."""

    def __init__(self, config_path: str, lattice):
        self._config = configparser.ConfigParser()
        self._config.read(config_path)
        self._lattice = lattice

        # Load analysis parameters
        self._violation_threshold = self._config.getint(
            "analysis", "violation_distance_threshold"
        )
        self._batch_window = self._config.getint(
            "analysis", "batch_window_seconds"
        )

    @property
    def violation_threshold(self):
        """Return the configured violation distance threshold."""
        return self._violation_threshold

    def detect_violations(
        self, events: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Detect information flow violations in the product lattice.

        A violation occurs when information flows to a dominating element
        in the product lattice and the distance between the source and
        destination exceeds the configured threshold.
        """
        violations = []

        for event in events:
            from_pair = (event["from_conf"], event["from_integ"])
            to_pair = (event["to_conf"], event["to_integ"])

            # Check if destination dominates source (upward flow)
            if not self._lattice.dominates(from_pair, to_pair):
                continue

            # Compute distance and check threshold
            distance = self._lattice.flow_distance(from_pair, to_pair)

            if distance > self._violation_threshold:
                # Compute combined classification for the flow
                combined = self._lattice.join(from_pair, to_pair)

                violations.append({
                    "event_id": event["event_id"],
                    "source_id": event["source_id"],
                    "entity": event["entity"],
                    "from_conf": event["from_conf"],
                    "from_integ": event["from_integ"],
                    "to_conf": event["to_conf"],
                    "to_integ": event["to_integ"],
                    "combined_conf": combined[0] if combined else None,
                    "combined_integ": combined[1] if combined else None,
                    "distance": distance,
                    "timestamp": event["timestamp"]
                })

        return violations

    def compute_flow_matrix(
        self, events: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, int]]:
        """
        Build a matrix of flow counts between confidentiality labels.

        Aggregates all flows by their source and destination
        confidentiality levels regardless of integrity dimension.
        """
        matrix: Dict[str, Dict[str, int]] = {}

        for event in events:
            from_l = event["from_conf"]
            to_l = event["to_conf"]

            if from_l not in matrix:
                matrix[from_l] = {}
            matrix[from_l][to_l] = matrix[from_l].get(to_l, 0) + 1

        return matrix

    def compute_source_volumes(
        self, events: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Compute total volume per source stream.
        """
        volumes: Dict[str, int] = {}
        for event in events:
            src = event["source_id"]
            volumes[src] = volumes.get(src, 0) + event["volume"]
        return volumes
