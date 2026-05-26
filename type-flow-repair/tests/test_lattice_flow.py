"""
Type Flow Analysis Verification Tests
======================================

Validates the correctness of the type flow analysis system by checking
the analysis output against expected results for each program specification.
"""

import json
import os
import pytest
from pathlib import Path


DATA_DIR = "/app/runtime/data"


def load_report(filename: str):
    """Load a JSON report file from the data directory."""
    filepath = os.path.join(DATA_DIR, filename)
    assert os.path.exists(filepath), f"Report file not found: {filepath}"
    with open(filepath, "r") as f:
        return json.load(f)


def load_main_report():
    """Load the main analysis report."""
    return load_report("analysis_report.json")


# ============================================================================
# Structural Tests (6 tests - always pass)
# ============================================================================

class TestOutputStructure:
    """Verify that analysis output files exist and have correct structure."""

    def test_main_report_exists(self):
        """Main analysis report file should exist."""
        path = os.path.join(DATA_DIR, "analysis_report.json")
        assert os.path.exists(path), "analysis_report.json not found"

    def test_main_report_has_required_fields(self):
        """Main report should have programs and summary."""
        report = load_main_report()
        assert "programs" in report
        assert "summary" in report
        assert isinstance(report["programs"], list)

    def test_four_programs_analyzed(self):
        """Exactly 4 program specifications should be analyzed."""
        report = load_main_report()
        assert report["summary"]["total_programs"] == 4

    def test_per_program_reports_exist(self):
        """Per-program report files should exist."""
        for name in ["program_alpha", "program_beta", "program_gamma", "program_delta"]:
            path = os.path.join(DATA_DIR, f"report_{name}.json")
            assert os.path.exists(path), f"Per-program report not found: report_{name}.json"

    def test_total_assignment_count(self):
        """Total assignments across all programs should be 36."""
        report = load_main_report()
        assert report["summary"]["total_assignments"] == 36

    def test_assignment_results_have_valid_field(self):
        """Each assignment result should have a valid boolean field."""
        report = load_main_report()
        for prog in report["programs"]:
            for assign in prog["assignments"]:
                assert "valid" in assign
                assert isinstance(assign["valid"], bool)


# ============================================================================
# Primitive and Generic Tests (6 tests - pass regardless of function variance)
# ============================================================================

class TestPrimitiveAndGenericSubtyping:
    """Tests for primitive hierarchy and generic covariance - always correct."""

    def test_alpha_primitive_hierarchy(self):
        """int should be assignable to float via numeric hierarchy."""
        report = load_report("report_program_alpha.json")
        assign = report["assignments"][6]
        assert assign["valid"] is True, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be valid in program_alpha"
        )

    def test_alpha_entity_hierarchy(self):
        """Dog should be assignable to Animal."""
        report = load_report("report_program_alpha.json")
        assign = report["assignments"][7]
        assert assign["valid"] is True, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be valid in program_alpha"
        )

    def test_delta_not_subtype_unrelated(self):
        """int should NOT be assignable to string (unrelated types)."""
        report = load_report("report_program_delta.json")
        assign = report["assignments"][2]
        assert assign["valid"] is False, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be invalid in program_delta"
        )

    def test_beta_covariant_generic(self):
        """List[Car] should be assignable to List[Vehicle] (covariant generics)."""
        report = load_report("report_program_beta.json")
        assign = report["assignments"][1]
        assert assign["valid"] is True, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be valid in program_beta"
        )

    def test_beta_generic_wrong_direction(self):
        """List[Vehicle] should NOT be assignable to List[Car]."""
        report = load_report("report_program_beta.json")
        assign = report["assignments"][2]
        assert assign["valid"] is False, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be invalid in program_beta"
        )

    def test_gamma_return_covariance(self):
        """Function with same params and covariant return (int <: number) should be valid."""
        report = load_report("report_program_gamma.json")
        assign = report["assignments"][6]
        assert assign["valid"] is True, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be valid in program_gamma"
        )


# ============================================================================
# Function Parameter Variance Tests (18 tests - FAIL with buggy code)
# ============================================================================

class TestFunctionParameterVariance:
    """Tests that require correct function parameter type checking to pass."""

    def test_alpha_animal_fn_to_dog_handler(self):
        """Function accepting Animal should be assignable to variable expecting function accepting Dog."""
        report = load_report("report_program_alpha.json")
        assign = report["assignments"][0]
        assert assign["valid"] is True, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be valid in program_alpha"
        )

    def test_alpha_dog_fn_not_to_animal_handler(self):
        """Function accepting Dog should NOT be assignable to variable expecting function accepting Animal."""
        report = load_report("report_program_alpha.json")
        assign = report["assignments"][1]
        assert assign["valid"] is False, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be invalid in program_alpha"
        )

    def test_alpha_animal_fn_to_cat_handler(self):
        """Function accepting Animal should be assignable to variable expecting function accepting Cat."""
        report = load_report("report_program_alpha.json")
        assign = report["assignments"][2]
        assert assign["valid"] is True, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be valid in program_alpha"
        )

    def test_alpha_object_fn_to_dog_handler(self):
        """Function accepting object should be assignable to variable expecting function accepting Dog."""
        report = load_report("report_program_alpha.json")
        assign = report["assignments"][3]
        assert assign["valid"] is True, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be valid in program_alpha"
        )

    def test_alpha_animal_fn_not_to_object_handler(self):
        """Function accepting Animal should NOT be assignable to variable expecting function accepting object."""
        report = load_report("report_program_alpha.json")
        assign = report["assignments"][4]
        assert assign["valid"] is False, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be invalid in program_alpha"
        )

    def test_beta_vehicle_fn_to_truck_var(self):
        """Function accepting Vehicle should be assignable to variable expecting function accepting Truck."""
        report = load_report("report_program_beta.json")
        assign = report["assignments"][3]
        assert assign["valid"] is True, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be valid in program_beta"
        )

    def test_beta_truck_fn_not_to_vehicle_var(self):
        """Function accepting Truck should NOT be assignable to variable expecting function accepting Vehicle."""
        report = load_report("report_program_beta.json")
        assign = report["assignments"][4]
        assert assign["valid"] is False, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be invalid in program_beta"
        )

    def test_beta_number_fn_to_int_fn(self):
        """Function (number)->int assigned to (int)->float should be valid."""
        report = load_report("report_program_beta.json")
        assign = report["assignments"][5]
        assert assign["valid"] is True, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be valid in program_beta"
        )

    def test_beta_list_animal_fn_to_dog_fn_list(self):
        """List[(Animal)->string] should be assignable to List[(Dog)->string]."""
        report = load_report("report_program_beta.json")
        assign = report["assignments"][6]
        assert assign["valid"] is True, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be valid in program_beta"
        )

    def test_beta_list_dog_fn_not_to_animal_fn_list(self):
        """List[(Dog)->string] should NOT be assignable to List[(Animal)->string]."""
        report = load_report("report_program_beta.json")
        assign = report["assignments"][7]
        assert assign["valid"] is False, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be invalid in program_beta"
        )

    def test_gamma_hof_source_narrower_return_invalid(self):
        """HOF where source has param with narrower return should be invalid."""
        report = load_report("report_program_gamma.json")
        assign = report["assignments"][0]
        assert assign["valid"] is False, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be invalid in program_gamma"
        )

    def test_gamma_hof_target_narrower_return_valid(self):
        """HOF where target has param with narrower return should be valid."""
        report = load_report("report_program_gamma.json")
        assign = report["assignments"][1]
        assert assign["valid"] is True, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be valid in program_gamma"
        )

    def test_gamma_nested_return_function_valid(self):
        """Function returning a broader-param function should be valid."""
        report = load_report("report_program_gamma.json")
        assign = report["assignments"][2]
        assert assign["valid"] is True, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be valid in program_gamma"
        )

    def test_gamma_wider_params_narrower_return(self):
        """Function (object)->Dog assigned to (Animal)->Animal should be valid."""
        report = load_report("report_program_gamma.json")
        assign = report["assignments"][4]
        assert assign["valid"] is True, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be valid in program_gamma"
        )

    def test_delta_number_fn_to_int_handler(self):
        """Function (number)->string assigned to (int)->string should be valid."""
        report = load_report("report_program_delta.json")
        assign = report["assignments"][0]
        assert assign["valid"] is True, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be valid in program_delta"
        )

    def test_delta_int_fn_not_to_number_handler(self):
        """Function (int)->string should NOT be assignable to (number)->string variable."""
        report = load_report("report_program_delta.json")
        assign = report["assignments"][1]
        assert assign["valid"] is False, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be invalid in program_delta"
        )

    def test_delta_multi_param_contravariant_valid(self):
        """Multi-param function (Animal,Vehicle)->bool assigned to (Dog,Car)->bool should be valid."""
        report = load_report("report_program_delta.json")
        assign = report["assignments"][7]
        assert assign["valid"] is True, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be valid in program_delta"
        )

    def test_delta_callback_contravariant_valid(self):
        """Function (Animal)->Cat assigned to (Cat)->Animal should be valid."""
        report = load_report("report_program_delta.json")
        assign = report["assignments"][11]
        assert assign["valid"] is True, (
            f"expected assignment '{assign['target']} = {assign['source']}' "
            f"to be valid in program_delta"
        )
