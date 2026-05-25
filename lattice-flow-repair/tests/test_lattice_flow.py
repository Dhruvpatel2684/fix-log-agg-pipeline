"""
Tests for abstract interval analysis system.

Validates that the interval domain correctly computes over-approximations
of program traces including branch merges, loop fixed points, and
nested control flow.
"""

import json
import os


OUTPUT_DIR = "/app/runtime/output"


def load_results():
    with open(os.path.join(OUTPUT_DIR, "analysis_results.json")) as f:
        return json.load(f)


def load_summary():
    with open(os.path.join(OUTPUT_DIR, "summary.json")) as f:
        return json.load(f)


class TestOutputGeneration:
    """Basic structural tests that always pass."""

    def test_analysis_output_exists(self):
        """Analysis results file must be generated."""
        assert os.path.isfile(os.path.join(OUTPUT_DIR, "analysis_results.json"))

    def test_summary_output_exists(self):
        """Summary file must be generated."""
        assert os.path.isfile(os.path.join(OUTPUT_DIR, "summary.json"))

    def test_all_traces_processed(self):
        """All four traces must be processed."""
        summary = load_summary()
        assert summary["total_traces"] == 4

    def test_beta_counter_lower_bound(self):
        """Loop counter must start from 0."""
        results = load_results()
        counter = results["trace_beta"]["variables"]["counter"]
        assert counter["lo"] == 0

    def test_beta_sum_lower_bound(self):
        """Loop sum must start from 0."""
        results = load_results()
        s = results["trace_beta"]["variables"]["sum"]
        assert s["lo"] == 0


class TestBranchMergeSoundness:
    """Tests that verify sound over-approximation at branch merge points.

    Abstract interpretation must produce a SOUND over-approximation:
    the abstract result must contain ALL possible concrete values.
    At a branch merge, values from EITHER path could occur, so the
    abstract value must encompass both branches.
    """

    def test_alpha_x_lower_bound(self):
        """Variable x after branch must include values from the else-path.

        The else-branch subtracts [1,4] from initial x=[0,10], giving
        values as low as -4. The merged result must include this.
        """
        results = load_results()
        x = results["trace_alpha"]["variables"]["x"]
        assert x["type"] == "interval"
        assert x["lo"] == -4, (
            f"expected x lower bound -4 after branch merge, got {x['lo']}"
        )

    def test_alpha_x_upper_bound(self):
        """Variable x after branch must include values from the then-path.

        The then-branch adds [2,3] to initial x=[0,10], giving values
        up to 13. The merged result must include this.
        """
        results = load_results()
        x = results["trace_alpha"]["variables"]["x"]
        assert x["hi"] == 13, (
            f"expected x upper bound 13 after branch merge, got {x['hi']}"
        )

    def test_alpha_z_not_bottom(self):
        """Variable z must not be empty after branch merge.

        Both branches assign a value to z, so z must be a non-empty
        interval after the merge point.
        """
        results = load_results()
        z = results["trace_alpha"]["variables"]["z"]
        assert z["type"] == "interval", (
            f"expected z to be a non-empty interval after merge, got {z['type']}"
        )

    def test_alpha_z_lower_bound(self):
        """Variable z must include the minimum value from either branch."""
        results = load_results()
        z = results["trace_alpha"]["variables"]["z"]
        assert z["lo"] == -5, (
            f"expected z lower bound -5, got {z['lo']}"
        )

    def test_alpha_z_upper_bound(self):
        """Variable z must include the maximum value from either branch."""
        results = load_results()
        z = results["trace_alpha"]["variables"]["z"]
        assert z["hi"] == 20, (
            f"expected z upper bound 20, got {z['hi']}"
        )

    def test_alpha_result_not_bottom(self):
        """The computed result must be a valid interval, not empty."""
        results = load_results()
        r = results["trace_alpha"]["variables"]["result"]
        assert r["type"] == "interval", (
            f"expected result to be an interval, got {r['type']}"
        )

    def test_alpha_result_bounds(self):
        """Result = x + z must reflect the full range of both operands."""
        results = load_results()
        r = results["trace_alpha"]["variables"]["result"]
        assert r["lo"] == -9, (
            f"expected result lower bound -9, got {r['lo']}"
        )
        assert r["hi"] == 33, (
            f"expected result upper bound 33, got {r['hi']}"
        )


class TestNestedBranchSoundness:
    """Tests for nested branch merge correctness."""

    def test_delta_a_lower_bound(self):
        """Variable a must reflect values from both outer branches."""
        results = load_results()
        a = results["trace_delta"]["variables"]["a"]
        assert a["lo"] == -18, (
            f"expected a lower bound -18, got {a['lo']}"
        )

    def test_delta_a_upper_bound(self):
        """Variable a must include values up to 20."""
        results = load_results()
        a = results["trace_delta"]["variables"]["a"]
        assert a["hi"] == 20, (
            f"expected a upper bound 20, got {a['hi']}"
        )

    def test_delta_c_includes_nested_then(self):
        """Variable c must include values from the nested then-branch [0,3]."""
        results = load_results()
        c = results["trace_delta"]["variables"]["c"]
        assert c["type"] == "interval"
        assert c["lo"] <= 0, (
            f"expected c lower bound <= 0, got {c['lo']}"
        )

    def test_delta_c_includes_nested_else(self):
        """Variable c must include values from the nested else-branch [7,15]."""
        results = load_results()
        c = results["trace_delta"]["variables"]["c"]
        assert c["hi"] >= 15, (
            f"expected c upper bound >= 15, got {c['hi']}"
        )

    def test_delta_total_bounds(self):
        """Total = a + c must reflect combined ranges."""
        results = load_results()
        t = results["trace_delta"]["variables"]["total"]
        assert t["lo"] == -20, (
            f"expected total lower bound -20, got {t['lo']}"
        )
        assert t["hi"] == 35, (
            f"expected total upper bound 35, got {t['hi']}"
        )

    def test_delta_product_upper_bound(self):
        """Product = b * c must account for max(c) = 15."""
        results = load_results()
        p = results["trace_delta"]["variables"]["product"]
        assert p["hi"] == 300, (
            f"expected product upper bound 300, got {p['hi']}"
        )


class TestLoopBranchInteraction:
    """Tests for branches inside loops."""

    def test_gamma_accum_not_singleton(self):
        """Accumulator in loop with branch must not be stuck at initial value.

        A loop body that can both increase and decrease a value via
        branching must produce a non-trivial interval for the accumulator.
        """
        results = load_results()
        accum = results["trace_gamma"]["variables"]["accum"]
        assert accum["type"] == "interval"
        is_trivial = (accum.get("lo") == 0 and accum.get("hi") == 0)
        assert not is_trivial, (
            "expected accum to be a non-trivial interval after loop with "
            "branching increment/decrement, but got [0,0]"
        )

    def test_gamma_accum_unbounded(self):
        """Accumulator must be unbounded after widening with divergent branch.

        Since the loop body can increment accum (then-branch) or decrement
        it (else-branch), the abstract iteration should widen to [-inf, +inf].
        """
        results = load_results()
        accum = results["trace_gamma"]["variables"]["accum"]
        assert accum.get("lo") is None or accum["lo"] <= -100, (
            f"expected accum lower bound to be unbounded, got {accum.get('lo')}"
        )
        assert accum.get("hi") is None or accum["hi"] >= 100, (
            f"expected accum upper bound to be unbounded, got {accum.get('hi')}"
        )
