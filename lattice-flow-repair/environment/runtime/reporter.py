"""
Report generator for product lattice flow analysis results.

Produces structured JSON reports including:
- Summary statistics (total events, violations, source volumes)
- Detailed violation records with combined classifications
- Flow matrix between confidentiality levels
"""

import json
import os
from typing import Dict, Any, List


def generate_reports(
    output_dir: str,
    events: List[Dict[str, Any]],
    deduplicated_events: List[Dict[str, Any]],
    violations: List[Dict[str, Any]],
    flow_matrix: Dict[str, Dict[str, int]],
    source_volumes: Dict[str, int]
) -> None:
    """Generate all output report files."""
    os.makedirs(output_dir, exist_ok=True)

    # Summary report
    summary = {
        "total_events_loaded": len(events),
        "events_after_dedup": len(deduplicated_events),
        "total_violations": len(violations),
        "source_volumes": source_volumes,
        "flow_matrix_size": len(flow_matrix)
    }

    summary_path = os.path.join(output_dir, "summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    # Violations report
    violations_report = {
        "violation_count": len(violations),
        "violations": violations
    }

    violations_path = os.path.join(output_dir, "violations.json")
    with open(violations_path, "w") as f:
        json.dump(violations_report, f, indent=2)

    # Flow matrix report
    matrix_path = os.path.join(output_dir, "flow_matrix.json")
    with open(matrix_path, "w") as f:
        json.dump(flow_matrix, f, indent=2)
