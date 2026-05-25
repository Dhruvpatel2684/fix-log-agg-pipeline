"""
Schedule satisfiability checker.

Validates whether a proposed schedule satisfies all temporal ordering
constraints after propagation. A schedule is satisfiable when:
1. All task windows remain non-empty after propagation
2. No ordering constraint is violated (predecessor finishes, then successor starts)
3. All task pairs connected by constraints have adequate separation

The checker uses the propagated bounds to determine satisfiability
and reports which constraints are violated if any.
"""

from typing import Dict, Any, List, Tuple
from runtime.intervals import intervals_overlap, compute_separation


class SatisfiabilityChecker:
    """Checks temporal constraint satisfiability for schedules."""

    def check_ordering_constraints(
        self,
        bounds: Dict[str, Dict[str, int]],
        constraints: List[Dict[str, str]]
    ) -> List[Dict[str, Any]]:
        """
        Check each ordering constraint for potential violations.

        For a 'before' constraint (A before B), we verify that there exists
        at least one valid assignment where A completes before B starts.
        The constraint is satisfiable if A's earliest end is separated from
        B's latest start — meaning SOME pairing of A's end and B's start
        respects the ordering.

        A constraint is violated when even the best case (A starts earliest,
        B starts latest) still results in temporal overlap.
        """
        violations = []

        for constraint in constraints:
            if constraint["type"] == "before":
                pred = constraint["from"]
                succ = constraint["to"]

                pred_earliest_end = bounds[pred]["earliest_end"]
                succ_latest_start = bounds[succ]["latest_start"]

                # Check if the predecessor's earliest completion overlaps
                # with the successor's latest possible start
                if intervals_overlap(pred_earliest_end, succ_latest_start):
                    separation = compute_separation(pred_earliest_end, succ_latest_start)
                    violations.append({
                        "constraint": f"{pred} before {succ}",
                        "pred_earliest_end": pred_earliest_end,
                        "succ_latest_start": succ_latest_start,
                        "separation": separation,
                        "satisfied": False
                    })
                else:
                    separation = compute_separation(pred_earliest_end, succ_latest_start)
                    violations.append({
                        "constraint": f"{pred} before {succ}",
                        "pred_earliest_end": pred_earliest_end,
                        "succ_latest_start": succ_latest_start,
                        "separation": separation,
                        "satisfied": True
                    })

        return violations

    def overall_satisfiability(
        self,
        feasible: bool,
        infeasible_tasks: List[str],
        constraint_results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Determine overall schedule satisfiability.

        A schedule is satisfiable iff:
        - All windows are non-empty (feasible = True)
        - All ordering constraints are satisfied
        """
        all_constraints_sat = all(c["satisfied"] for c in constraint_results)
        satisfiable = feasible and all_constraints_sat

        violated = [c["constraint"] for c in constraint_results if not c["satisfied"]]

        return {
            "satisfiable": satisfiable,
            "feasible_windows": feasible,
            "infeasible_tasks": infeasible_tasks,
            "constraints_satisfied": all_constraints_sat,
            "violated_constraints": violated,
            "constraint_details": constraint_results
        }
