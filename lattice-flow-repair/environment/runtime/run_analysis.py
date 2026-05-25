"""
Entry point for the lattice-based information flow analysis system.

Orchestrates the loading, analysis, and reporting stages:
1. Initialize security lattice from configuration
2. Load and merge department flow events
3. Filter to monitored departments
4. Analyze flows for security violations
5. Compute flow volumes and matrices
6. Generate structured reports
"""

import os
import sys

# Ensure runtime package is importable
sys.path.insert(0, "/app")

from runtime.lattice import SecurityLattice
from runtime.loader import load_department_events, validate_event_schema
from runtime.analyzer import FlowAnalyzer
from runtime.reporter import generate_reports


def main():
    """Run the full information flow analysis."""
    config_path = "/app/runtime/config.ini"
    data_dir = "/app/runtime/data"
    output_dir = "/app/runtime/output"

    # Initialize lattice and analyzer
    lattice = SecurityLattice(config_path)
    analyzer = FlowAnalyzer(config_path, lattice)

    # Load all department events
    events = load_department_events(data_dir)

    # Validate schema
    valid_events = [e for e in events if validate_event_schema(e)]

    # Filter to monitored departments only
    monitored_events = [
        e for e in valid_events if analyzer.is_monitored(e["source_id"])
    ]

    # Detect violations
    violations = analyzer.detect_violations(monitored_events)

    # Compute flow matrix
    flow_matrix = analyzer.compute_flow_matrix(monitored_events)

    # Compute window volumes
    window_volumes = analyzer.compute_window_volumes(monitored_events)

    # Generate reports
    generate_reports(
        output_dir=output_dir,
        events=valid_events,
        monitored_events=monitored_events,
        violations=violations,
        flow_matrix=flow_matrix,
        window_volumes=window_volumes
    )

    print(f"Analysis complete. Reports written to {output_dir}")
    print(f"  Total events: {len(valid_events)}")
    print(f"  Monitored: {len(monitored_events)}")
    print(f"  Violations: {len(violations)}")


if __name__ == "__main__":
    main()
