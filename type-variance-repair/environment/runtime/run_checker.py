"""Entry point for the type variance checking system.

Orchestrates the full process:
1. Parse type definitions from source data files
2. Register type hierarchy and generic declarations
3. Check all type assignments for variance correctness
4. Resolve type variable constraints
5. Generate output reports
"""
import os
import sys

from runtime.type_parser import TypeParser
from runtime.variance_checker import VarianceChecker
from runtime.constraint_solver import ConstraintSolver
from runtime.reporter import Reporter


def main():
    """Run the type variance checking system end-to-end."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config.ini")

    # Stage 1: Parse type records from data files
    parser = TypeParser(config_path)
    records = parser.parse_all(base_dir)

    # Stage 2: Register type hierarchy
    checker = VarianceChecker(config_path)
    checker.register_types(records)

    # Stage 3: Check all assignments
    assignment_results = []
    assignments = sorted(
        [r for r in records if r.kind == "assignment"],
        key=lambda r: (r.timestamp, r.source_module, r.seq),
    )

    for record in assignments:
        result = checker.check_assignment(record.target, record.source)
        assignment_results.append({
            "id": record.id,
            "source_module": record.source_module,
            "target": record.target,
            "source": record.source,
            "context": record.context,
            "valid": result["valid"],
            "reason": result["reason"],
            "priority": record.priority,
            "timestamp": record.timestamp,
            "seq": record.seq,
        })

    # Stage 4: Resolve constraints
    solver = ConstraintSolver()
    solver.collect_constraints(records)
    constraint_results = solver.get_all_resolutions()

    # Stage 5: Generate reports
    reporter = Reporter(config_path)
    reporter.generate_reports(assignment_results, constraint_results, base_dir)

    print(f"Type checking complete. Processed {len(records)} records.")
    print(f"  Assignments checked: {len(assignment_results)}")
    print(f"  Constraints resolved: {len(constraint_results)}")


if __name__ == "__main__":
    main()
