"""
Report generator for flow analysis results.

Produces structured JSON reports including:
- Summary statistics (total events, violations, monitored flows)
- Detailed violation records
- Flow volume matrix between security labels
"""

import json
import os
from typing import Dict, Any, List


def generate_reports(
    output_dir: str,
    events: List[Dict[str, Any]],
    monitored_events: List[Dict[str, Any]],
    violations: List[Dict[str, Any]],
    flow_matrix: Dict[str, Dict[str, int]],
    window_volumes: Dict[str, int]
) -> None:
    """Generate all output report files."""
    os.makedirs(output_dir, exist_ok=True)

    # Summary report
    summary = {
        "total_events_loaded": len(events),
        "monitored_events": len(monitored_events),
        "total_violations": len(violations),
        "entities_with_volume": len(window_volumes),
        "flow_matrix_sources": len(flow_matrix)
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

    # Volume report
    volume_report = {
        "entity_volumes": window_volumes
    }
    volume_path = os.path.join(output_dir, "volumes.json")
    with open(volume_path, "w") as f:
        json.dump(volume_report, f, indent=2)
