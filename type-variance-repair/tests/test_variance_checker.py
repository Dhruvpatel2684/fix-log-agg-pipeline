"""Tests for the type variance checking system.

Validates correct operation of type parsing, declaration-site variance
checking, constraint resolution via greatest lower bound, and
deterministic report generation across multiple source modules.
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
    """Structural tests verifying output files exist with correct format."""

    def test_output_directory_exists(self):
        """The output directory must be created during processing."""
        assert os.path.isdir(OUTPUT_DIR), (
            f"Output directory {OUTPUT_DIR} was not created"
        )

    def test_all_report_files_generated(self):
        """All three report files must be present after processing."""
        for fname in ["assignments_report.json", "constraints_report.json", "summary.json"]:
            path = os.path.join(OUTPUT_DIR, fname)
            assert os.path.isfile(path), f"Expected output file {fname} not found"

    def test_summary_schema_fields(self):
        """Summary report must contain all required aggregate fields."""
        summary = load_json("summary.json")
        for field in ["total_checked", "valid_assignments", "invalid_assignments",
                      "violations", "constraint_count"]:
            assert field in summary, f"Missing field '{field}' in summary"

    def test_assignment_record_schema(self):
        """Each assignment record must contain all required fields."""
        report = load_json("assignments_report.json")
        assert isinstance(report["assignments"], list)
        if report["assignments"]:
            rec = report["assignments"][0]
            for field in ["id", "source_module", "target", "source",
                          "context", "valid", "reason"]:
                assert field in rec, f"Assignment record missing '{field}'"


class TestModuleInclusion:
    """Tests verifying correct source module filtering."""

    def test_total_assignment_count(self):
        """All configured modules must contribute records to the output."""
        report = load_json("assignments_report.json")
        assert report["total_assignments"] == 31, (
            f"Expected 31 assignments from all configured modules, "
            f"got {report['total_assignments']}"
        )

    def test_all_modules_present_in_output(self):
        """Records from all four configured modules must appear."""
        report = load_json("assignments_report.json")
        modules = set(a["source_module"] for a in report["assignments"])
        expected = {"core_types", "collections", "io_handlers", "functional"}
        assert modules == expected, (
            f"Expected modules {expected}, found {modules}"
        )


class TestDeclarationSiteVariance:
    """Tests verifying declaration-site variance semantics.

    In declaration-site variance, the subtyping direction for a generic
    type's argument is determined by the variance annotation declared
    on the generic type parameter itself, NOT by the position where
    the assignment occurs (parameter vs return_value context).
    """

    def test_covariant_in_parameter_position_valid(self):
        """A covariant type used in parameter position must still use covariant rules.

        Producer is declared covariant. Producer<Cat> assigned to Producer<Animal>
        in a parameter context must be VALID because Cat <: Animal and
        the declared variance is covariant (subtype preserved).
        """
        report = load_json("assignments_report.json")
        rec = next((a for a in report["assignments"] if a["id"] == "CT020"), None)
        assert rec is not None, "Record CT020 not found"
        assert rec["valid"] is True, (
            f"CT020 should be valid: covariant container in parameter position "
            f"still uses declaration-site covariant rules. Got: {rec['reason']}"
        )

    def test_contravariant_in_return_position_valid(self):
        """A contravariant type used in return position must still use contravariant rules.

        Consumer is declared contravariant. Consumer<Animal> assigned to
        Consumer<Cat> in return_value context must be VALID because
        Cat <: Animal and contravariant reverses direction.
        """
        report = load_json("assignments_report.json")
        rec = next((a for a in report["assignments"] if a["id"] == "CT021"), None)
        assert rec is not None, "Record CT021 not found"
        assert rec["valid"] is True, (
            f"CT021 should be valid: contravariant container in return position "
            f"still uses declaration-site contravariant rules. Got: {rec['reason']}"
        )

    def test_covariant_in_parameter_position_invalid(self):
        """A covariant container with wrong direction must be invalid regardless of context.

        Producer<Animal> assigned to Producer<Cat> in parameter position:
        covariant requires source_arg <: target_arg, Animal <: Cat is false.
        Must be INVALID even though parameter context would suggest contravariant.
        """
        report = load_json("assignments_report.json")
        rec = next((a for a in report["assignments"] if a["id"] == "CT022"), None)
        assert rec is not None, "Record CT022 not found"
        assert rec["valid"] is False, (
            f"CT022 should be invalid: covariant declared type, "
            f"Animal is not subtype of Cat. Got: {rec['reason']}"
        )

    def test_contravariant_in_return_position_invalid(self):
        """A contravariant container with wrong direction must be invalid regardless of context.

        Consumer<Cat> assigned to Consumer<Animal> in return_value position:
        contravariant requires target_arg <: source_arg, Animal <: Cat is false.
        Must be INVALID even though return context would suggest covariant.
        """
        report = load_json("assignments_report.json")
        rec = next((a for a in report["assignments"] if a["id"] == "CT023"), None)
        assert rec is not None, "Record CT023 not found"
        assert rec["valid"] is False, (
            f"CT023 should be invalid: contravariant declared type, "
            f"Animal is not subtype of Cat. Got: {rec['reason']}"
        )


class TestConstraintResolution:
    """Tests verifying greatest-lower-bound constraint resolution.

    When multiple type bounds exist for a type variable in a scope,
    the resolver must select the most specific (narrowest/deepest in
    the hierarchy) bound — the greatest lower bound in the type lattice.
    """

    def test_process_animals_resolves_to_most_specific(self):
        """T1 in fn:process_animals has bounds [Cat, Siamese]. Must resolve to Siamese."""
        report = load_json("constraints_report.json")
        rec = next(
            (r for r in report["resolutions"]
             if r["scope"] == "fn:process_animals" and r["type_var"] == "T1"),
            None
        )
        assert rec is not None, "Resolution for T1/fn:process_animals not found"
        assert rec["resolved_bound"] == "Siamese", (
            f"Expected most specific bound 'Siamese' (depth 3), "
            f"got '{rec['resolved_bound']}'"
        )

    def test_merge_lists_resolves_to_most_specific(self):
        """E1 in fn:merge_lists has bounds [List, MutableList]. Must resolve to MutableList."""
        report = load_json("constraints_report.json")
        rec = next(
            (r for r in report["resolutions"]
             if r["scope"] == "fn:merge_lists" and r["type_var"] == "E1"),
            None
        )
        assert rec is not None, "Resolution for E1/fn:merge_lists not found"
        assert rec["resolved_bound"] == "MutableList", (
            f"Expected most specific bound 'MutableList' (depth 3), "
            f"got '{rec['resolved_bound']}'"
        )

    def test_read_all_resolves_to_most_specific(self):
        """R1 in fn:read_all has bounds [InputStream, BufferedInput]. Must resolve to BufferedInput."""
        report = load_json("constraints_report.json")
        rec = next(
            (r for r in report["resolutions"]
             if r["scope"] == "fn:read_all" and r["type_var"] == "R1"),
            None
        )
        assert rec is not None, "Resolution for R1/fn:read_all not found"
        assert rec["resolved_bound"] == "BufferedInput", (
            f"Expected most specific bound 'BufferedInput' (depth 3), "
            f"got '{rec['resolved_bound']}'"
        )


class TestDeterministicOutput:
    """Tests verifying deterministic ordering and aggregate correctness."""

    def test_cross_module_timestamp_ordering(self):
        """Records sharing a timestamp must be ordered by source_module then seq."""
        report = load_json("assignments_report.json")
        ts = "2024-01-15T10:01:00Z"
        same_ts = [a for a in report["assignments"] if a["timestamp"] == ts]
        # With all 4 modules included, should have records from each
        assert len(same_ts) >= 4, (
            f"Expected at least 4 records at {ts}, got {len(same_ts)}"
        )
        modules_order = [a["source_module"] for a in same_ts]
        assert modules_order == sorted(modules_order), (
            f"Records at {ts} not in deterministic module order: {modules_order}"
        )

    def test_total_violations_count(self):
        """With all bugs fixed, exactly 13 assignments must be violations."""
        summary = load_json("summary.json")
        assert summary["invalid_assignments"] == 13, (
            f"Expected 13 violations, got {summary['invalid_assignments']}"
        )
