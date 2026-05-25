import json
import os
import pytest


OUTPUT_DIR = "/app/runtime/output"


def load_results():
    path = os.path.join(OUTPUT_DIR, "schedule_analysis.json")
    with open(path) as f:
        return json.load(f)


def load_summary():
    path = os.path.join(OUTPUT_DIR, "summary.json")
    with open(path) as f:
        return json.load(f)


class TestOutputGeneration:

    def test_analysis_output_exists(self):
        path = os.path.join(OUTPUT_DIR, "schedule_analysis.json")
        assert os.path.isfile(path), "expected analysis output to be generated"

    def test_summary_output_exists(self):
        path = os.path.join(OUTPUT_DIR, "summary.json")
        assert os.path.isfile(path), "expected summary output to be generated"

    def test_total_scenarios_processed(self):
        summary = load_summary()
        assert summary["total_scenarios"] == 4, (
            f"expected 4 scenarios processed, got {summary['total_scenarios']}"
        )


class TestSatisfiabilityResults:

    def test_delta_unsatisfiable(self):
        results = load_results()
        assert results["delta"]["satisfiable"] is False, (
            "expected satisfiable=false for scenario delta"
        )

    def test_alpha_satisfiable(self):
        results = load_results()
        assert results["alpha"]["satisfiable"] is True, (
            "expected satisfiable=true for scenario alpha, got false"
        )

    def test_beta_satisfiable(self):
        results = load_results()
        assert results["beta"]["satisfiable"] is True, (
            "expected satisfiable=true for scenario beta, got false"
        )

    def test_gamma_satisfiable(self):
        results = load_results()
        assert results["gamma"]["satisfiable"] is True, (
            "expected satisfiable=true for scenario gamma, got false"
        )


class TestPropagatedBounds:

    def test_alpha_build_latest_end(self):
        results = load_results()
        bounds = results["alpha"]["propagated_bounds"]
        assert bounds["build"]["latest_end"] == 10, (
            f"expected build latest_end=10 for alpha, got {bounds['build']['latest_end']}"
        )

    def test_beta_integration_earliest_start(self):
        results = load_results()
        bounds = results["beta"]["propagated_bounds"]
        assert bounds["integration"]["earliest_start"] == 15, (
            f"expected integration earliest_start=15 for beta, "
            f"got {bounds['integration']['earliest_start']}"
        )

    def test_beta_release_earliest_start(self):
        results = load_results()
        bounds = results["beta"]["propagated_bounds"]
        assert bounds["release"]["earliest_start"] == 21, (
            f"expected release earliest_start=21 for beta, "
            f"got {bounds['release']['earliest_start']}"
        )

    def test_gamma_phase3_earliest_start(self):
        results = load_results()
        bounds = results["gamma"]["propagated_bounds"]
        assert bounds["phase3"]["earliest_start"] == 18, (
            f"expected phase3 earliest_start=18 for gamma, "
            f"got {bounds['phase3']['earliest_start']}"
        )

    def test_gamma_review_earliest_start(self):
        results = load_results()
        bounds = results["gamma"]["propagated_bounds"]
        assert bounds["review"]["earliest_start"] == 23, (
            f"expected review earliest_start=23 for gamma, "
            f"got {bounds['review']['earliest_start']}"
        )

    def test_gamma_phase2_earliest_start(self):
        results = load_results()
        bounds = results["gamma"]["propagated_bounds"]
        assert bounds["phase2"]["earliest_start"] == 10, (
            f"expected phase2 earliest_start=10 for gamma, "
            f"got {bounds['phase2']['earliest_start']}"
        )


class TestConstraintDetails:

    def test_alpha_no_violated_constraints(self):
        results = load_results()
        violated = results["alpha"]["violated_constraints"]
        assert len(violated) == 0, (
            f"expected no violated constraints for alpha, got {len(violated)}"
        )

    def test_beta_all_constraints_satisfied(self):
        results = load_results()
        assert results["beta"]["constraints_satisfied"] is True, (
            "expected all constraints satisfied for beta"
        )

    def test_delta_has_infeasible_tasks(self):
        results = load_results()
        assert len(results["delta"]["infeasible_tasks"]) > 0, (
            "expected infeasible tasks for delta"
        )
