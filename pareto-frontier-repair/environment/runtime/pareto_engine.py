"""
Pareto Engine - Main entrypoint for multi-objective optimization analysis.

Reads an objectives file, processes solutions through the dominance engine,
performs frontier analysis, and writes output files.

Output files:
- /app/runtime/pareto_state.jsonl: Per-solution normalized objective state
- /app/runtime/pareto_report.json: Frontier analysis summary with fingerprint
"""

import os
import sys

# Ensure runtime directory is in path
runtime_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, runtime_dir)

from objective_parser import parse_objective_file, get_evaluator_ids, get_objective_count
from dominance_engine import DominanceEngine
from frontier_analyzer import FrontierAnalyzer
from report_writer import write_pareto_state, write_pareto_report


def main():
    """Main processing flow."""
    # Locate input file
    objectives_path = os.path.join(runtime_dir, "objectives.txt")

    if not os.path.exists(objectives_path):
        print(f"ERROR: Objectives file not found at {objectives_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[pareto_engine] Loading objectives from {objectives_path}")

    # Step 1: Parse solutions
    solutions = parse_objective_file(objectives_path)
    evaluator_ids = get_evaluator_ids(solutions)
    obj_count = get_objective_count(solutions)
    print(f"[pareto_engine] Parsed {len(solutions)} solutions across {len(evaluator_ids)} evaluators")

    # Step 2: Normalize objectives through dominance engine
    engine = DominanceEngine(obj_count)
    solution_objectives = engine.process_all(solutions)
    print(f"[pareto_engine] Objectives normalized for all solutions")

    # Step 3: Frontier analysis
    analyzer = FrontierAnalyzer(solution_objectives)
    analyzer.analyze()
    print(f"[pareto_engine] Frontier analysis complete: "
          f"{analyzer.get_dominance_count()} dominance pairs, "
          f"{analyzer.get_nondominated_count()} non-dominated pairs")

    # Step 4: Write outputs
    state_path = os.path.join(runtime_dir, "pareto_state.jsonl")
    report_path = os.path.join(runtime_dir, "pareto_report.json")

    write_pareto_state(solution_objectives, state_path)
    write_pareto_report(analyzer, solution_objectives, evaluator_ids, report_path)

    print(f"[pareto_engine] Output written to:")
    print(f"  - {state_path}")
    print(f"  - {report_path}")
    print(f"[pareto_engine] Done.")


if __name__ == "__main__":
    main()
