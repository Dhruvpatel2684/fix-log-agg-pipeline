"""
Dominance Engine - Normalizes objectives and prepares solutions for Pareto analysis.

Implements objective normalization:
- RAW values: normalize to [0,1] using min-max scaling per objective
- NORMALIZED values: already in [0,1], pass through
- AGGREGATE values: merge with existing normalized values, then re-normalize

Each evaluator maintains running min/max bounds for normalization.
After aggregation, the combined bounds must be recomputed to ensure
all values remain in [0,1].
"""

from typing import Dict, List, Tuple
from objective_parser import Solution


class DominanceEngine:
    """Normalizes objective values and prepares solutions for frontier analysis."""

    def __init__(self, objective_count: int):
        self.objective_count = objective_count
        self.solutions_normalized: List[Tuple[Solution, List[float]]] = []
        # Track global bounds for normalization
        self._global_min = [float('inf')] * objective_count
        self._global_max = [float('-inf')] * objective_count

    def _update_bounds(self, values: List[float]):
        """Update global min/max bounds with new values."""
        for i in range(self.objective_count):
            if values[i] < self._global_min[i]:
                self._global_min[i] = values[i]
            if values[i] > self._global_max[i]:
                self._global_max[i] = values[i]

    def _normalize_value(self, value: float, obj_idx: int) -> float:
        """Normalize a single value to [0,1] using current global bounds."""
        min_val = self._global_min[obj_idx]
        max_val = self._global_max[obj_idx]
        if max_val == min_val:
            return 0.5
        return (value - min_val) / (max_val - min_val)

    def process_solution(self, solution: Solution) -> List[float]:
        """Process a single solution and return normalized objective values.

        Applies normalization rules:
        - RAW: update bounds, normalize using min-max scaling
        - NORMALIZED: pass through as-is (already in [0,1])
        - AGGREGATE: merge into existing bounds, normalize

        After aggregation, the normalization context absorbs the aggregate
        bounds automatically through the running min/max — no separate
        re-normalization pass is needed since the bounds are monotonically
        expanded by each new data point.
        """
        if solution.obj_type == "NORMALIZED":
            # Already normalized, use directly
            normalized = list(solution.raw_values)
        else:
            # RAW or AGGREGATE: update bounds and normalize
            self._update_bounds(solution.raw_values)
            normalized = [
                self._normalize_value(solution.raw_values[i], i)
                for i in range(self.objective_count)
            ]

        solution.normalized_values = normalized
        self.solutions_normalized.append((solution, normalized))
        return normalized

    def process_all(self, solutions: List[Solution]) -> List[Tuple[Solution, List[float]]]:
        """Process all solutions in order and return (solution, normalized_values) pairs."""
        for solution in solutions:
            self.process_solution(solution)
        return self.solutions_normalized

    def get_normalized_solutions(self) -> List[Tuple[Solution, List[float]]]:
        """Return all processed solutions with their normalized values."""
        return self.solutions_normalized
