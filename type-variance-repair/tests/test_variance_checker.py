"""Tests for the type variance checking system.

Validates correct operation of parsing, variance-aware assignment checking,
constraint resolution, and deterministic report generation.
"""
import json
import os

OUTPUT_DIR = "/app/runtime/output"


def load_json(filename):
    """Load a JSON output file from the output directory."""
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "r") as f:
        return json.load(f)


class TestOutputStructure:
    """Structural tests that verify output files exist and have correct format."""

    def test_output_directory_exists(self):
        """Verify the output directory was created by the type checker."""
        assert os.path.isdir(OUTPUT_DIR), (
            f"Output directory {OUTPUT_DIR} does not exist. "
            "The type checker may not have been run."
        )

    def test_all_report_files_present(self):
        """Verify all three expected output files are generated."""
        expected_files = [
            "assignments_report.json",
            "constraints_report.json",
            "summary.json",
        ]
        for fname in expected_files:
            path = os.path.join(OUTPUT_DIR, fname)
            assert os.path.isfile(path), (
                f"Missing output file: {fname}. "
                "Check that /app/runtime/reporter.py generates all reports."
            )

    def test_summary_has_required_fields(self):
        """Verify summary.json contains all required schema fields."""
        summary = load_json("summary.json")
        required_fields = [
            "total_checked",
            "valid_assignments",
            "invalid_assignments",
            "violations",
            "constraint_count",
        ]
        for field in required_fields:
            assert field in summary, (
                f"summary.json missing required field '{field}'. "
                "Check /app/runtime/reporter.py _write_summary method."
            )

    def test_assignments_report_structure(self):
        """Verify assignments_report.json contains total and assignments list."""
        report = load_json("assignments_report.json")
        assert "total_assignments" in report, (
            "assignments_report.json missing 'total_assignments' field"
        )
        assert "assignments" in report, (
            "assignments_report.json missing 'assignments' field"
        )
        assert isinstance(report["assignments"], list), (
            "'assignments' field must be a list"
        )
        # Each assignment must have required fields
        if report["assignments"]:
            first = report["assignments"][0]
            for field in ["id", "source_module", "target", "source", "valid", "reason"]:
                assert field in first, (
                    f"Assignment record missing field '{field}'"
                )


class TestSourceModuleInclusion:
    """Tests that verify all configured source modules are processed."""

    def test_total_records_includes_all_modules(self):
        """Verify that all four source modules are included in processing.

        The configuration lists: core_types, collections, io_handlers, functional.
        All four must be parsed and included. Check the module list in
        /app/runtime/config.ini [sources] section for correct parsing.
        """
        report = load_json("assignments_report.json")
        assert report["total_assignments"] == 27, (
            f"Expected 27 total assignments (from all 4 modules), "
            f"got {report['total_assignments']}. "
            "Check that /app/runtime/type_parser.py correctly parses the "
            "modules list from /app/runtime/config.ini [sources] section."
        )

    def test_functional_module_present(self):
        """Verify records from the 'functional' source module are included."""
        report = load_json("assignments_report.json")
        modules_present = set(
            a["source_module"] for a in report["assignments"]
        )
        assert "functional" in modules_present, (
            "The 'functional' module records are missing from output. "
            "Check how /app/runtime/type_parser.py splits the modules config "
            "value in /app/runtime/config.ini."
        )

    def test_all_four_modules_represented(self):
        """Verify all four modules have records in the output."""
        report = load_json("assignments_report.json")
        modules_present = set(
            a["source_module"] for a in report["assignments"]
        )
        expected = {"core_types", "collections", "io_handlers", "functional"}
        assert modules_present == expected, (
            f"Expected modules {expected}, got {modules_present}. "
            "Check /app/runtime/config.ini modules list parsing."
        )


class TestVarianceChecking:
    """Tests for correct variance-aware assignability decisions."""

    def test_contravariant_valid_assignment(self):
        """Verify that Consumer<Animal> -> Consumer<Cat> is VALID (contravariant).

        For a contravariant container like Consumer<T>, the direction reverses:
        if Cat <: Animal, then Consumer<Animal> is assignable to Consumer<Cat>.
        The check must verify target_arg <: source_arg (Cat <: Animal = true).
        """
        report = load_json("assignments_report.json")
        ct014 = next(
            (a for a in report["assignments"] if a["id"] == "CT014"), None
        )
        assert ct014 is not None, "Assignment CT014 not found in output"
        assert ct014["valid"] is True, (
            f"CT014: Consumer<Animal> -> Consumer<Cat> should be VALID. "
            f"For contravariant, target_arg (Cat) must be subtype of source_arg "
            f"(Animal). Cat <: Animal is true. Got: {ct014['reason']}. "
            "Check the contravariant branch in "
            "/app/runtime/variance_checker.py _check_variance_assignability."
        )

    def test_contravariant_invalid_assignment(self):
        """Verify that Consumer<Cat> -> Consumer<Animal> is INVALID (contravariant).

        For contravariant: need target_arg <: source_arg.
        Target is Consumer<Animal>, source is Consumer<Cat>.
        Check: Animal <: Cat? NO. So this should be invalid.
        """
        report = load_json("assignments_report.json")
        ct012 = next(
            (a for a in report["assignments"] if a["id"] == "CT012"), None
        )
        assert ct012 is not None, "Assignment CT012 not found in output"
        assert ct012["valid"] is False, (
            f"CT012: Consumer<Cat> -> Consumer<Animal> should be INVALID. "
            f"For contravariant, target_arg (Animal) must be subtype of "
            f"source_arg (Cat). Animal is NOT subtype of Cat. "
            f"Got: {ct012['reason']}. "
            "Check /app/runtime/variance_checker.py contravariant logic."
        )

    def test_handler_contravariant_from_functional(self):
        """Verify Handler<Predicate> -> Handler<Callable> valid in functional module.

        Handler is contravariant. Target=Handler<Predicate>, Source=Handler<Callable>.
        Contravariant check: target_arg(Predicate) <: source_arg(Callable)?
        Yes, Predicate extends Callable. So this is VALID.
        Requires functional module to be included.
        """
        report = load_json("assignments_report.json")
        fn007 = next(
            (a for a in report["assignments"] if a["id"] == "FN007"), None
        )
        assert fn007 is not None, (
            "Assignment FN007 not found - functional module may be missing. "
            "Check /app/runtime/type_parser.py module list parsing."
        )
        assert fn007["valid"] is True, (
            f"FN007: Handler<Callable> -> Handler<Predicate> should be VALID. "
            f"Contravariant: Predicate <: Callable. Got: {fn007['reason']}. "
            "Check /app/runtime/variance_checker.py contravariant logic."
        )


class TestConstraintResolution:
    """Tests for correct type variable constraint resolution."""

    def test_constraint_last_write_wins(self):
        """Verify that constraint resolution uses last-write-wins semantics.

        Within a scope, multiple constraints for the same type variable
        should resolve to the HIGHEST priority bound only, not accumulate.
        """
        report = load_json("constraints_report.json")
        fn_process = next(
            (r for r in report["resolutions"]
             if r["scope"] == "fn:process_animals" and r["type_var"] == "T1"),
            None,
        )
        assert fn_process is not None, (
            "Missing constraint resolution for T1 in scope fn:process_animals"
        )
        assert fn_process["resolved_bound"] == "Siamese", (
            f"T1 in fn:process_animals should resolve to 'Siamese' "
            f"(highest priority=4), got '{fn_process['resolved_bound']}'. "
            "Check /app/runtime/constraint_solver.py - constraints should use "
            "last-write-wins, not accumulate bounds."
        )

    def test_constraint_priority_value(self):
        """Verify that resolved constraint has the correct priority value."""
        report = load_json("constraints_report.json")
        fn_merge = next(
            (r for r in report["resolutions"]
             if r["scope"] == "fn:merge_lists" and r["type_var"] == "E1"),
            None,
        )
        assert fn_merge is not None, (
            "Missing constraint resolution for E1 in scope fn:merge_lists"
        )
        assert fn_merge["priority"] == 3, (
            f"E1 in fn:merge_lists should have priority 3 (the winning "
            f"constraint's priority), got {fn_merge['priority']}. "
            "Check /app/runtime/constraint_solver.py accumulation logic."
        )


class TestDeterministicOrdering:
    """Tests for deterministic output ordering across source modules."""

    def test_same_timestamp_ordering(self):
        """Verify deterministic ordering when records share a timestamp.

        Records at timestamp '2024-01-15T10:01:00Z' come from multiple
        modules (collections, core_types, functional, io_handlers).
        They must be sorted by (timestamp, source_module, seq) for
        deterministic output. Check /app/runtime/run_checker.py sort key.
        """
        report = load_json("assignments_report.json")
        # Find all assignments at the shared timestamp
        ts = "2024-01-15T10:01:00Z"
        same_ts = [a for a in report["assignments"] if a["timestamp"] == ts]
        assert len(same_ts) == 4, (
            f"Expected 4 assignments at {ts} (one from each module), "
            f"got {len(same_ts)}. Check source module inclusion."
        )
        # Verify ordering: collections < core_types < functional < io_handlers
        modules_in_order = [a["source_module"] for a in same_ts]
        expected_order = ["collections", "core_types", "functional", "io_handlers"]
        assert modules_in_order == expected_order, (
            f"Records at {ts} are not in deterministic order. "
            f"Expected {expected_order}, got {modules_in_order}. "
            "Check sort key in /app/runtime/run_checker.py - needs "
            "source_module as tiebreaker between timestamp and seq."
        )

    def test_violation_count_correct(self):
        """Verify the total number of violations is correct after all fixes."""
        summary = load_json("summary.json")
        assert summary["invalid_assignments"] == 11, (
            f"Expected 11 invalid assignments, got {summary['invalid_assignments']}. "
            "This requires all variance checks and module inclusion to be correct."
        )
