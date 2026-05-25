"""
Entry point for the temporal schedule analysis system.

Orchestrates scenario loading, constraint propagation, satisfiability
checking, and report generation for each configured scheduling scenario.
"""

import json
import os
import sys
import configparser
from typing import List, Dict

sys.path.insert(0, "/app")

from runtime.propagator import ConstraintPropagator
from runtime.checker import SatisfiabilityChecker


def load_scenarios(data_dir: str, active: List[str]) -> List[Dict]:
    """Load scenario files matching active list."""
    scenarios = []
    for filename in sorted(os.listdir(data_dir)):
        if not filename.endswith("_scenario.json"):
            continue
        with open(os.path.join(data_dir, filename)) as f:
            scenario = json.load(f)
        if scenario["scenario_id"] in active:
            scenarios.append(scenario)
    return scenarios


def main():
    """Run temporal schedule analysis for all configured scenarios."""
    config_path = "/app/runtime/config.ini"
    data_dir = "/app/runtime/data"

    config = configparser.ConfigParser()
    config.read(config_path)

    output_dir = config.get("analysis", "output_dir")
    active_list = [s.strip() for s in config.get("analysis", "active_scenarios").split(",")]

    os.makedirs(output_dir, exist_ok=True)

    propagator = ConstraintPropagator(config_path)
    checker = SatisfiabilityChecker()

    scenarios = load_scenarios(data_dir, active_list)

    results = {}
    for scenario in scenarios:
        sid = scenario["scenario_id"]
        tasks = scenario["tasks"]
        constraints = scenario["constraints"]

        # Propagate constraints
        bounds = propagator.propagate(tasks, constraints)

        # Check feasibility
        feasible, infeasible_tasks = propagator.check_feasibility(bounds)

        # Check ordering constraints
        constraint_results = checker.check_ordering_constraints(bounds, constraints)

        # Determine overall satisfiability
        result = checker.overall_satisfiability(feasible, infeasible_tasks, constraint_results)
        result["scenario_id"] = sid
        result["propagated_bounds"] = bounds

        results[sid] = result

    # Write results
    output_path = os.path.join(output_dir, "schedule_analysis.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    # Write summary
    summary = {
        "total_scenarios": len(scenarios),
        "satisfiable_count": sum(1 for r in results.values() if r["satisfiable"]),
        "unsatisfiable_count": sum(1 for r in results.values() if not r["satisfiable"]),
        "scenario_results": {sid: r["satisfiable"] for sid, r in results.items()}
    }
    summary_path = os.path.join(output_dir, "summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Analysis complete. Results written to {output_dir}")
    for sid, r in results.items():
        status = "satisfiable" if r["satisfiable"] else "UNSATISFIABLE"
        print(f"  {sid}: {status}")


if __name__ == "__main__":
    main()
