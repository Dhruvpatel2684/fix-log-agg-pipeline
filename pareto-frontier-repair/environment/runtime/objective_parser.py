"""
Objective data parser for multi-objective optimization results.

Parses the pipe-delimited objective file format and produces typed solution
records for downstream processing by the dominance engine.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple


@dataclass
class Solution:
    """Represents a single solution evaluation in objective space."""
    solution_id: str
    evaluator: str
    obj_type: str  # RAW, NORMALIZED, AGGREGATE
    raw_values: List[float] = field(default_factory=list)
    normalized_values: List[float] = field(default_factory=list)


def parse_objective_file(filepath: str) -> List[Solution]:
    """Parse an objectives file and return a list of Solution objects.

    Solutions are returned in file order. The parser handles three types:
    - RAW: values need normalization before comparison
    - NORMALIZED: already in [0,1] range, ready for comparison
    - AGGREGATE: combined from multiple evaluators, needs re-normalization
    """
    solutions = []

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Objectives file not found: {filepath}")

    with open(filepath, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            parts = line.split("|")
            if len(parts) != 4:
                raise ValueError(
                    f"Malformed record at line {line_num}: expected 4 pipe-delimited fields, "
                    f"got {len(parts)}"
                )

            solution_id, evaluator, obj_type, raw_values_str = parts

            # Validate obj_type
            if obj_type not in ("RAW", "NORMALIZED", "AGGREGATE"):
                raise ValueError(
                    f"Unknown objective type at line {line_num}: '{obj_type}'"
                )

            # Parse values
            try:
                values = [float(v.strip()) for v in raw_values_str.split(",")]
            except ValueError:
                raise ValueError(
                    f"Invalid numeric values at line {line_num}: '{raw_values_str}'"
                )

            solution = Solution(
                solution_id=solution_id,
                evaluator=evaluator,
                obj_type=obj_type,
                raw_values=values,
            )

            solutions.append(solution)

    return solutions


def get_evaluator_ids(solutions: List[Solution]) -> List[str]:
    """Extract unique evaluator IDs from solution list, sorted."""
    return sorted(set(s.evaluator for s in solutions))


def get_objective_count(solutions: List[Solution]) -> int:
    """Return the number of objectives (dimensions) in the problem."""
    if solutions:
        return len(solutions[0].raw_values)
    return 0
