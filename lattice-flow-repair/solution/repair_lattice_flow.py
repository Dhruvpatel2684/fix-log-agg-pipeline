"""
Repair script for the anomaly correlation engine.
Fixes the causal independence check to account for temporal propagation
constraints in addition to structural graph reachability.
"""

import re

CORRELATOR_PATH = "/app/runtime/correlator.py"

# Read the current source
with open(CORRELATOR_PATH, "r") as f:
    source = f.read()

# The buggy _check_independence method only checks structural reachability.
# It needs to also verify that the time elapsed between events is sufficient
# for the signal to propagate along the shortest path in the dependency graph.

old_method = '''    def _check_independence(
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
        return not forward_reachable and not backward_reachable'''

new_method = '''    def _check_independence(
        self, event_a: AnomalyEvent, event_b: AnomalyEvent
    ) -> bool:
        """
        Determine if two events are causally independent based on the
        service dependency graph structure and temporal propagation constraints.

        Two events are considered causally independent if there is no
        timing-feasible directed path between their services. Even if a
        structural path exists, the events are independent if the elapsed
        time is less than the minimum propagation delay along that path.

        Args:
            event_a: First anomaly event
            event_b: Second anomaly event

        Returns:
            True if the events are causally independent,
            False if a potential causal relationship exists.
        """
        source_service = event_a.service_id
        target_service = event_b.service_id

        if source_service == target_service:
            return False

        # Check forward direction: can event_a have caused event_b?
        forward_reachable = self._graph.is_reachable(source_service, target_service)
        forward_feasible = False
        if forward_reachable and event_a.timestamp_ms <= event_b.timestamp_ms:
            min_delay = self._graph.minimum_propagation_delay(source_service, target_service)
            elapsed = event_b.timestamp_ms - event_a.timestamp_ms
            if min_delay is not None and elapsed >= min_delay:
                forward_feasible = True

        # Check backward direction: can event_b have caused event_a?
        backward_reachable = self._graph.is_reachable(target_service, source_service)
        backward_feasible = False
        if backward_reachable and event_b.timestamp_ms <= event_a.timestamp_ms:
            min_delay = self._graph.minimum_propagation_delay(target_service, source_service)
            elapsed = event_a.timestamp_ms - event_b.timestamp_ms
            if min_delay is not None and elapsed >= min_delay:
                backward_feasible = True

        # Independent if no timing-feasible causal path exists in either direction
        return not forward_feasible and not backward_feasible'''

if old_method in source:
    source = source.replace(old_method, new_method)
    with open(CORRELATOR_PATH, "w") as f:
        f.write(source)
    print("Successfully repaired _check_independence in correlator.py")
    print("Added temporal propagation delay verification to causal independence check")
else:
    print("ERROR: Could not find the target method to patch")
    print("The source code may have already been modified")
    exit(1)
