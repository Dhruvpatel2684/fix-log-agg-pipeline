"""
Entry point for the product lattice information flow analysis system.

Orchestrates the loading, deduplication, analysis, and reporting stages:
1. Initialize product lattice from configuration
2. Load and merge source flow event streams
3. Deduplicate events within the configured window
4. Analyze flows for security violations using product lattice ordering
5. Compute flow matrices and volumes
6. Generate structured reports
"""

import sys

sys.path.insert(0, "/app")

from runtime.lattice import ProductLattice
from runtime.loader import load_source_events, deduplicate_events, validate_event_schema
from runtime.analyzer import FlowAnalyzer
from runtime.reporter import generate_reports
import configparser


def main():
    """Run the full product lattice flow analysis."""
    config_path = "/app/runtime/config.ini"
    data_dir = "/app/runtime/data"

    config = configparser.ConfigParser()
    config.read(config_path)

    output_dir = config.get("reporting", "output_dir")
    dedup_window = config.getint("sources", "dedup_window_seconds")

    # Initialize lattice and analyzer
    lattice = ProductLattice(config_path)
    analyzer = FlowAnalyzer(config_path, lattice)

    # Load all source events
    events = load_source_events(data_dir)

    # Validate schema
    valid_events = [e for e in events if validate_event_schema(e)]

    # Deduplicate within window
    deduped_events = deduplicate_events(valid_events, dedup_window)

    # Detect violations
    violations = analyzer.detect_violations(deduped_events)

    # Compute flow matrix
    flow_matrix = analyzer.compute_flow_matrix(deduped_events)

    # Compute source volumes
    source_volumes = analyzer.compute_source_volumes(deduped_events)

    # Generate reports
    generate_reports(
        output_dir=output_dir,
        events=valid_events,
        deduplicated_events=deduped_events,
        violations=violations,
        flow_matrix=flow_matrix,
        source_volumes=source_volumes
    )

    print(f"Analysis complete. Reports written to {output_dir}")
    print(f"  Total events: {len(valid_events)}")
    print(f"  After dedup: {len(deduped_events)}")
    print(f"  Violations: {len(violations)}")


if __name__ == "__main__":
    main()
