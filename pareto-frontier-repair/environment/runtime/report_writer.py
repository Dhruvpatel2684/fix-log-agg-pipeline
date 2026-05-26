"""
Report writer for Pareto frontier analysis output.

Produces two output files:
- pareto_state.jsonl: Per-solution state (one JSON object per line)
- pareto_report.json: Summary report with statistics and fingerprint
"""

import json
import hashlib
from typing import Dict, List, Tuple
from objective_parser import Solution
from frontier_analyzer import FrontierAnalyzer


def write_pareto_state(solution_objectives: List[Tuple[Solution, List[float]]],
                       output_path: str):
    """Write per-solution state to a JSONL file.

    Each line contains:
    - solution_index: position in processing order
    - solution_id: unique identifier
    - evaluator: which evaluator produced this
    - obj_type: RAW/NORMALIZED/AGGREGATE
    - normalized_objectives: objectives after normalization
    """
    with open(output_path, "w") as f:
        for idx, (solution, normalized) in enumerate(solution_objectives):
            record = {
                "solution_index": idx,
                "solution_id": solution.solution_id,
                "evaluator": solution.evaluator,
                "obj_type": solution.obj_type,
                "normalized_objectives": [round(v, 6) for v in normalized],
            }
            f.write(json.dumps(record, sort_keys=True) + "\n")


def compute_frontier_fingerprint(analyzer: FrontierAnalyzer,
                                  solution_objectives: List[Tuple[Solution, List[float]]]) -> str:
    """Compute a deterministic fingerprint of the dominance graph.

    The fingerprint encodes the complete dominance structure:
    - All dominance edges (dominator -> dominated)
    - All non-dominated pairs (sorted lexicographically)
    - Solution identifiers use solution_id format

    This allows quick detection of frontier drift between evaluations.
    """
    n = len(solution_objectives)
    edges = []

    for i in range(n):
        for j in range(i + 1, n):
            si = solution_objectives[i]
            sj = solution_objectives[j]
            id_i = si[0].solution_id
            id_j = sj[0].solution_id

            obj_i = si[1]
            obj_j = sj[1]

            # Determine relationship using the same logic as analyzer
            from frontier_analyzer import dominates, are_nondominated
            if are_nondominated(obj_i, obj_j):
                pair = tuple(sorted([id_i, id_j]))
                edges.append((pair[0], pair[1], "nondominated"))
            elif dominates(obj_i, obj_j):
                edges.append((id_i, id_j, "dominates"))
            elif dominates(obj_j, obj_i):
                edges.append((id_j, id_i, "dominates"))
            else:
                # Remaining incomparable solutions — resolved by index order
                edges.append((id_i, id_j, "dominates"))

    edges.sort()
    fingerprint_data = json.dumps(edges, sort_keys=True)
    return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]


def write_pareto_report(analyzer: FrontierAnalyzer,
                        solution_objectives: List[Tuple[Solution, List[float]]],
                        evaluator_ids: List[str],
                        output_path: str):
    """Write the Pareto analysis summary report."""
    # Count solutions per evaluator
    solutions_per_evaluator = {}
    for solution, _ in solution_objectives:
        ev = solution.evaluator
        solutions_per_evaluator[ev] = solutions_per_evaluator.get(ev, 0) + 1

    # Compute fingerprint
    fingerprint = compute_frontier_fingerprint(analyzer, solution_objectives)

    report = {
        "evaluator_ids": sorted(evaluator_ids),
        "total_solutions": len(solution_objectives),
        "solutions_per_evaluator": solutions_per_evaluator,
        "dominance_count": analyzer.get_dominance_count(),
        "nondominated_count": analyzer.get_nondominated_count(),
        "frontier_ranking": analyzer.get_frontier_ranking(),
        "asymmetry_holds": analyzer.verify_asymmetry(),
        "frontier_fingerprint": fingerprint,
    }

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
