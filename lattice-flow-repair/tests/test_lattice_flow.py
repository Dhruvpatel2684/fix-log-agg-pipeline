"""
Tests for the lattice-based information flow analysis system.

Validates that the security lattice correctly processes department flow
events, detects violations at the proper threshold, computes accurate
flow volumes, and produces well-structured output reports.
"""

import json
import os


OUTPUT_DIR = "/app/runtime/output"


class TestOutputFilesExist:
    """Verify that the analysis produces all expected output files."""

    def test_summary_file_exists(self):
        """The analysis must produce a summary.json report file."""
        path = os.path.join(OUTPUT_DIR, "summary.json")
        assert os.path.exists(path), (
            f"Expected summary report at {path}. "
            "Check that /app/runtime/run_analysis.py completes without error."
        )

    def test_violations_file_exists(self):
        """The analysis must produce a violations.json report file."""
        path = os.path.join(OUTPUT_DIR, "violations.json")
        assert os.path.exists(path), (
            f"Expected violations report at {path}. "
            "Check that /app/runtime/run_analysis.py completes without error."
        )

    def test_flow_matrix_file_exists(self):
        """The analysis must produce a flow_matrix.json report file."""
        path = os.path.join(OUTPUT_DIR, "flow_matrix.json")
        assert os.path.exists(path), (
            f"Expected flow matrix at {path}. "
            "Check that /app/runtime/run_analysis.py completes without error."
        )

    def test_volumes_file_exists(self):
        """The analysis must produce a volumes.json report file."""
        path = os.path.join(OUTPUT_DIR, "volumes.json")
        assert os.path.exists(path), (
            f"Expected volumes report at {path}. "
            "Check that /app/runtime/run_analysis.py completes without error."
        )


class TestSummaryStructure:
    """Verify the summary report has correct structure and event counts."""

    def test_summary_has_required_fields(self):
        """Summary must contain all required statistical fields."""
        path = os.path.join(OUTPUT_DIR, "summary.json")
        with open(path) as f:
            summary = json.load(f)
        required_fields = [
            "total_events_loaded",
            "monitored_events",
            "total_violations",
            "entities_with_volume",
            "flow_matrix_sources"
        ]
        for field in required_fields:
            assert field in summary, (
                f"Missing field '{field}' in summary.json. "
                f"Expected fields: {required_fields}"
            )

    def test_total_events_loaded(self):
        """All 54 events from three department sources must be loaded."""
        path = os.path.join(OUTPUT_DIR, "summary.json")
        with open(path) as f:
            summary = json.load(f)
        assert summary["total_events_loaded"] == 54, (
            f"Expected 54 total events (18 per department x 3 departments), "
            f"got {summary['total_events_loaded']}. "
            "Check /app/runtime/loader.py loads all *_flows.json files."
        )


class TestDepartmentMonitoring:
    """Verify all configured departments are correctly monitored."""

    def test_monitored_event_count(self):
        """All 54 events should be from monitored departments including compliance.

        The configuration lists four monitored departments: engineering,
        research, operations, and compliance. All loaded events belong to
        one of these departments, so monitored_events should equal
        total_events_loaded.
        """
        path = os.path.join(OUTPUT_DIR, "summary.json")
        with open(path) as f:
            summary = json.load(f)
        assert summary["monitored_events"] == 54, (
            f"Expected 54 monitored events (all departments are monitored), "
            f"got {summary['monitored_events']}. "
            "Check that department name parsing in /app/runtime/analyzer.py "
            "correctly handles all entries in the monitored_departments config list."
        )

    def test_flow_matrix_includes_restricted_label(self):
        """Flow matrix must include 'restricted' as a source label.

        Compliance department events flow from the 'restricted' label.
        If compliance is correctly monitored, 'restricted' must appear
        as a key in the flow matrix.
        """
        path = os.path.join(OUTPUT_DIR, "flow_matrix.json")
        with open(path) as f:
            matrix = json.load(f)
        assert "restricted" in matrix, (
            f"Flow matrix is missing 'restricted' source label. "
            f"Found sources: {list(matrix.keys())}. "
            "Compliance department events use 'restricted' as from_label. "
            "Verify department filtering in /app/runtime/analyzer.py."
        )


class TestViolationDetection:
    """Verify security violation detection uses correct thresholds."""

    def test_violations_detected(self):
        """The system must detect violations when flow distance meets threshold.

        Under strict analysis mode, the violation threshold is 2. Any
        information flow crossing 2 or more lattice levels constitutes
        a violation. With the test data, this produces 27 violations.
        """
        path = os.path.join(OUTPUT_DIR, "violations.json")
        with open(path) as f:
            report = json.load(f)
        assert report["violation_count"] == 27, (
            f"Expected 27 violations under strict analysis threshold (distance >= 2), "
            f"got {report['violation_count']}. "
            "Check which configuration section provides the violation_threshold "
            "in /app/runtime/analyzer.py — strict mode uses [analysis.strict]."
        )

    def test_violation_record_structure(self):
        """Each violation record must contain all required fields."""
        path = os.path.join(OUTPUT_DIR, "violations.json")
        with open(path) as f:
            report = json.load(f)
        assert len(report["violations"]) > 0, "No violations found"
        violation = report["violations"][0]
        required = [
            "event_id", "source_id", "entity", "from_label",
            "to_label", "combined_label", "distance", "timestamp"
        ]
        for field in required:
            assert field in violation, (
                f"Violation record missing field '{field}'. "
                f"Found: {list(violation.keys())}"
            )

    def test_violation_combined_label_is_upper_bound(self):
        """Combined label must be the JOIN (least upper bound) of the two flow labels.

        In lattice-based security, when information from two classification
        levels merges, the combined classification is the supremum (join) —
        the HIGHER of the two levels in a total order. This ensures combined
        information receives at least the highest protection level of its inputs.

        For the flow internal->secret, the combined label must be 'secret'
        (the higher label), not 'internal' (the lower label).
        """
        path = os.path.join(OUTPUT_DIR, "violations.json")
        with open(path) as f:
            report = json.load(f)
        # Find a violation with from=internal, to=secret
        target = None
        for v in report["violations"]:
            if v["from_label"] == "internal" and v["to_label"] == "secret":
                target = v
                break
        assert target is not None, (
            "No violation found for flow internal->secret. "
            "Check violation detection in /app/runtime/analyzer.py."
        )
        assert target["combined_label"] == "secret", (
            f"Combined label for internal->secret should be 'secret' (the join/supremum), "
            f"got '{target['combined_label']}'. "
            "The combined classification in a security lattice is the LEAST UPPER BOUND "
            "(join), not the greatest lower bound (meet). "
            "Check combined_label() in /app/runtime/lattice.py."
        )


class TestFlowVolumes:
    """Verify flow volume computation across time windows."""

    def test_entity_volume_not_accumulated(self):
        """Entity volumes must reflect final window value, not sum across windows.

        Volume counters represent running totals that update with each window
        snapshot. When an entity appears in multiple time windows, only the
        most recent window's value is the correct current volume.

        'design-doc-alpha' appears in windows 0, 1, and 3 with values 37, 9, 16.
        The correct final volume is 16 (last window), not 62 (sum of all).
        """
        path = os.path.join(OUTPUT_DIR, "volumes.json")
        with open(path) as f:
            report = json.load(f)
        volumes = report["entity_volumes"]
        assert "design-doc-alpha" in volumes, (
            "Entity 'design-doc-alpha' missing from volumes report."
        )
        assert volumes["design-doc-alpha"] == 16, (
            f"Volume for 'design-doc-alpha' should be 16 (final window value), "
            f"got {volumes['design-doc-alpha']}. "
            "Check window volume computation in /app/runtime/analyzer.py — "
            "volumes should reflect the last window snapshot, not accumulate across windows."
        )

    def test_experiment_alpha_volume(self):
        """Experiment-alpha volume must reflect its final window snapshot value.

        'experiment-alpha' appears across multiple time windows.
        The correct volume is 9 (final window), not the accumulated total.
        """
        path = os.path.join(OUTPUT_DIR, "volumes.json")
        with open(path) as f:
            report = json.load(f)
        volumes = report["entity_volumes"]
        assert "experiment-alpha" in volumes, (
            "Entity 'experiment-alpha' missing from volumes report."
        )
        assert volumes["experiment-alpha"] == 9, (
            f"Volume for 'experiment-alpha' should be 9 (final window value), "
            f"got {volumes['experiment-alpha']}. "
            "Window volume computation should use last-write-wins semantics."
        )
