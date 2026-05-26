#!/usr/bin/env python3
"""
Oracle solution for pareto-frontier-repair task.

Fixes the 4 bugs:
1. dominance_engine.py: Must use two-pass normalization (compute all bounds first, then normalize)
2. frontier_analyzer.py: dominates() must use WEAK Pareto dominance (all>=, at least one>)
3. frontier_analyzer.py: Frontier ranking uses non-dominated sorting, not lexicographic
4. report_writer.py: Fingerprint uses the same fixed logic from bugs 2+3

This script re-processes the objectives with correct logic and overwrites the output files.
"""

import os
import sys
import json
import hashlib

# Ensure runtime directory is in path
runtime_dir = "/app/runtime"
sys.path.insert(0, runtime_dir)

from objective_parser import parse_objective_file, get_evaluator_ids, get_objective_count, Solution
from typing import Dict, List, Tuple, Set


# ============================================================
# Fixed Dominance Engine (Bug 1 fix: two-pass normalization)
# ============================================================

class FixedDominanceEngine:
    """Two-pass normalization: compute bounds first, then normalize all."""

    def __init__(self, obj_count):
        self.obj_count = obj_count
        self.solutions_normalized = []
        self._global_min = [float('inf')] * obj_count
        self._global_max = [float('-inf')] * obj_count

    def process_all(self, solutions):
        # Pass 1: compute global bounds from all RAW and AGGREGATE solutions
        for s in solutions:
            if s.obj_type in ("RAW", "AGGREGATE"):
                for i in range(self.obj_count):
                    if s.raw_values[i] < self._global_min[i]:
                        self._global_min[i] = s.raw_values[i]
                    if s.raw_values[i] > self._global_max[i]:
                        self._global_max[i] = s.raw_values[i]

        # Pass 2: normalize all solutions using final global bounds
        for s in solutions:
            if s.obj_type == "NORMALIZED":
                normalized = list(s.raw_values)
            else:
                normalized = []
                for i in range(self.obj_count):
                    mn, mx = self._global_min[i], self._global_max[i]
                    if mx == mn:
                        normalized.append(0.5)
                    else:
                        normalized.append((s.raw_values[i] - mn) / (mx - mn))
            s.normalized_values = normalized
            self.solutions_normalized.append((s, normalized))
        return self.solutions_normalized


# ============================================================
# Fixed Dominance (Bug 2 fix: weak Pareto dominance)
# ============================================================

def dominates_fixed(obj_a: List[float], obj_b: List[float]) -> bool:
    """Correct Pareto dominance: all >= AND at least one >."""
    all_geq = all(a >= b for a, b in zip(obj_a, obj_b))
    any_gt = any(a > b for a, b in zip(obj_a, obj_b))
    return all_geq and any_gt


def are_nondominated_fixed(obj_a: List[float], obj_b: List[float]) -> bool:
    """Correct: NEITHER dominates the other."""
    return not dominates_fixed(obj_a, obj_b) and not dominates_fixed(obj_b, obj_a)


# ============================================================
# Fixed Frontier Ranking (Bug 3 fix: non-dominated sorting)
# ============================================================

def compute_nds_ranking(sol_objs, dominates_fn) -> List[int]:
    """Non-dominated sorting (NSGA-II style) with ID tiebreak."""
    n = len(sol_objs)
    remaining = set(range(n))
    ranking = []

    while remaining:
        front = []
        for i in remaining:
            dominated = False
            for j in remaining:
                if i == j:
                    continue
                if dominates_fn(sol_objs[j][1], sol_objs[i][1]):
                    dominated = True
                    break
            if not dominated:
                front.append(i)

        front.sort(key=lambda idx: sol_objs[idx][0].solution_id)
        ranking.extend(front)
        remaining -= set(front)

    return ranking


# ============================================================
# Fixed Fingerprint (Bug 4 fix: uses corrected dominance)
# ============================================================

def compute_fingerprint_fixed(sol_objs) -> str:
    """Compute fingerprint with correct dominance logic."""
    n = len(sol_objs)
    edges = []

    for i in range(n):
        for j in range(i + 1, n):
            id_i = sol_objs[i][0].solution_id
            id_j = sol_objs[j][0].solution_id
            obj_i = sol_objs[i][1]
            obj_j = sol_objs[j][1]

            if are_nondominated_fixed(obj_i, obj_j):
                pair = tuple(sorted([id_i, id_j]))
                edges.append((pair[0], pair[1], "nondominated"))
            elif dominates_fixed(obj_i, obj_j):
                edges.append((id_i, id_j, "dominates"))
            elif dominates_fixed(obj_j, obj_i):
                edges.append((id_j, id_i, "dominates"))
            else:
                pair = tuple(sorted([id_i, id_j]))
                edges.append((pair[0], pair[1], "nondominated"))

    edges.sort()
    fingerprint_data = json.dumps(edges, sort_keys=True)
    return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]


# ============================================================
# Main
# ============================================================

def main():
    objectives_path = os.path.join(runtime_dir, "objectives.txt")

    # Parse solutions
    solutions = parse_objective_file(objectives_path)
    evaluator_ids = get_evaluator_ids(solutions)
    obj_count = get_objective_count(solutions)

    # Process with fixed normalization
    engine = FixedDominanceEngine(obj_count)
    sol_objs = engine.process_all(solutions)

    # Analyze with fixed dominance
    n = len(sol_objs)
    dom_pairs = []
    nondom_pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            oi = sol_objs[i][1]
            oj = sol_objs[j][1]
            if dominates_fixed(oi, oj):
                dom_pairs.append((i, j))
            elif dominates_fixed(oj, oi):
                dom_pairs.append((j, i))
            else:
                nondom_pairs.append((i, j))

    # Fixed ranking
    ranking = compute_nds_ranking(sol_objs, dominates_fixed)

    # Verify asymmetry
    dom_set = set(dom_pairs)
    asymmetry = all((j, i) not in dom_set for i, j in dom_pairs)

    # Compute fixed fingerprint
    fingerprint = compute_fingerprint_fixed(sol_objs)

    # Write pareto_state.jsonl
    state_path = os.path.join(runtime_dir, "pareto_state.jsonl")
    with open(state_path, "w") as f:
        for idx, (solution, normalized) in enumerate(sol_objs):
            record = {
                "solution_index": idx,
                "solution_id": solution.solution_id,
                "evaluator": solution.evaluator,
                "obj_type": solution.obj_type,
                "normalized_objectives": [round(v, 6) for v in normalized],
            }
            f.write(json.dumps(record, sort_keys=True) + "\n")

    # Write pareto_report.json
    solutions_per_evaluator = {}
    for solution, _ in sol_objs:
        ev = solution.evaluator
        solutions_per_evaluator[ev] = solutions_per_evaluator.get(ev, 0) + 1

    report = {
        "evaluator_ids": sorted(evaluator_ids),
        "total_solutions": len(sol_objs),
        "solutions_per_evaluator": solutions_per_evaluator,
        "dominance_count": len(dom_pairs),
        "nondominated_count": len(nondom_pairs),
        "frontier_ranking": ranking,
        "asymmetry_holds": asymmetry,
        "frontier_fingerprint": fingerprint,
    }

    report_path = os.path.join(runtime_dir, "pareto_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)

    print(f"[repair] Fixed processing complete:")
    print(f"  Dominance pairs: {len(dom_pairs)}")
    print(f"  Non-dominated pairs: {len(nondom_pairs)}")
    print(f"  Fingerprint: {fingerprint}")


if __name__ == "__main__":
    main()
