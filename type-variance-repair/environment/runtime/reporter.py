"""Report generator for type checking results.

Produces structured JSON output files containing:
- assignments_report.json: detailed results of all type assignment checks
- constraints_report.json: resolved type variable bounds
- summary.json: aggregate statistics and violation list
"""
import json
import os
import configparser


class Reporter:
    """Generates output reports from type checking and constraint resolution."""

    def __init__(self, config_path):
        self._config = configparser.ConfigParser()
        self._config.read(config_path)
        self._output_dir = self._config.get("sources", "output_dir")
        self._batch_size = self._config.getint("resolution", "batch_size")

    def generate_reports(self, assignment_results, constraint_results, base_dir):
        """Generate all output reports.

        Args:
            assignment_results: list of assignment check results
            constraint_results: list of resolved constraints
            base_dir: base directory for output
        """
        output_path = os.path.join(base_dir, self._output_dir)
        os.makedirs(output_path, exist_ok=True)

        self._write_assignments_report(assignment_results, output_path)
        self._write_constraints_report(constraint_results, output_path)
        self._write_summary(assignment_results, constraint_results, output_path)

    def _write_assignments_report(self, results, output_path):
        """Write detailed assignment checking results."""
        # Process in batches for memory efficiency
        batched_results = []
        for i in range(0, len(results), self._batch_size):
            batch = results[i:i + self._batch_size]
            batched_results.extend(batch)

        report = {
            "total_assignments": len(batched_results),
            "assignments": batched_results,
        }

        filepath = os.path.join(output_path, "assignments_report.json")
        with open(filepath, "w") as f:
            json.dump(report, f, indent=2)

    def _write_constraints_report(self, results, output_path):
        """Write constraint resolution results."""
        report = {
            "total_constraints": len(results),
            "resolutions": results,
        }

        filepath = os.path.join(output_path, "constraints_report.json")
        with open(filepath, "w") as f:
            json.dump(report, f, indent=2)

    def _write_summary(self, assignment_results, constraint_results, output_path):
        """Write summary with aggregate statistics."""
        valid_count = sum(1 for r in assignment_results if r["valid"])
        invalid_count = len(assignment_results) - valid_count

        violations = [
            {
                "id": r["id"],
                "target": r["target"],
                "source": r["source"],
                "reason": r["reason"],
                "source_module": r["source_module"],
            }
            for r in assignment_results
            if not r["valid"]
        ]

        # Sort violations for deterministic output
        violations.sort(
            key=lambda v: (v["id"])
        )

        summary = {
            "total_checked": len(assignment_results),
            "valid_assignments": valid_count,
            "invalid_assignments": invalid_count,
            "violations": violations,
            "constraint_count": len(constraint_results),
        }

        filepath = os.path.join(output_path, "summary.json")
        with open(filepath, "w") as f:
            json.dump(summary, f, indent=2)
