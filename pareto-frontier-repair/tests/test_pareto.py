"""
Test suite for Pareto frontier analysis system.

14 tests in 4 tiers:
- Tier 1 (6 tests): Structural checks - pass with buggy code
- Tier 2 (3 tests): Normalization checks - need Bug 1 fixed
- Tier 3 (3 tests): Dominance/ranking checks - need Bugs 2+3 fixed
- Tier 4 (2 tests): Full consistency checks - need all bugs fixed
"""

import json
import os
import hashlib

# Output file paths
RUNTIME_DIR = "/app/runtime"
STATE_PATH = os.path.join(RUNTIME_DIR, "pareto_state.jsonl")
REPORT_PATH = os.path.join(RUNTIME_DIR, "pareto_report.json")


def load_state():
    """Load pareto_state.jsonl as a list of dicts."""
    records = []
    with open(STATE_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_report():
    """Load pareto_report.json."""
    with open(REPORT_PATH, "r") as f:
        return json.load(f)


# =============================================================================
# TIER 1: Structural tests (pass with buggy code)
# =============================================================================

class TestTier1Structural:
    """Basic structural checks that pass even with buggy dominance logic."""

    def test_output_files_exist(self):
        """Both output files must exist after processing."""
        assert os.path.exists(STATE_PATH), f"Missing: {STATE_PATH}"
        assert os.path.exists(REPORT_PATH), f"Missing: {REPORT_PATH}"

    def test_three_evaluators_in_output(self):
        """Report must identify exactly 3 evaluators."""
        report = load_report()
        assert len(report["evaluator_ids"]) == 3

    def test_evaluator_ids_correct(self):
        """Evaluator IDs must be eval_alpha, eval_beta, eval_gamma."""
        report = load_report()
        assert report["evaluator_ids"] == ["eval_alpha", "eval_beta", "eval_gamma"]

    def test_solutions_per_evaluator(self):
        """Each evaluator must have the correct solution count."""
        report = load_report()
        spe = report["solutions_per_evaluator"]
        assert spe["eval_alpha"] == 9, f"eval_alpha expected 9, got {spe['eval_alpha']}"
        assert spe["eval_beta"] == 9, f"eval_beta expected 9, got {spe['eval_beta']}"
        assert spe["eval_gamma"] == 9, f"eval_gamma expected 9, got {spe['eval_gamma']}"

    def test_report_has_required_fields(self):
        """Report must contain all required fields."""
        report = load_report()
        required = [
            "evaluator_ids", "total_solutions", "solutions_per_evaluator",
            "dominance_count", "nondominated_count", "frontier_ranking",
            "asymmetry_holds", "frontier_fingerprint"
        ]
        for field in required:
            assert field in report, f"Missing field: {field}"

    def test_total_solutions_count(self):
        """Total solution count must be 27."""
        report = load_report()
        assert report["total_solutions"] == 27
        state = load_state()
        assert len(state) == 27


# =============================================================================
# TIER 2: Normalization tests (need Bug 1 fixed - must re-normalize after bounds)
# =============================================================================

class TestTier2Normalization:
    """Tests that verify correct objective normalization."""

    def test_normalized_values_in_range(self):
        """After correct normalization, ALL values must be in [0, 1].

        If RAW solutions are normalized incrementally without recomputing
        bounds after seeing all data, early solutions may have values
        outside [0,1] or values that don't reflect the true global range.
        AGGREGATE solutions shift the bounds, requiring re-normalization.
        """
        state = load_state()
        for record in state:
            for i, val in enumerate(record["normalized_objectives"]):
                assert 0.0 <= val <= 1.0, (
                    f"Solution {record['solution_id']} objective {i} = {val} "
                    f"is outside [0,1]. This suggests incremental normalization "
                    f"without a final re-normalization pass."
                )

    def test_extreme_solutions_at_boundaries(self):
        """Solutions with global min/max values must normalize to exactly 0 or 1.

        With correct two-pass normalization:
        - The solution with the minimum raw value on an objective gets 0.0
        - The solution with the maximum raw value on an objective gets 1.0

        If normalization is incremental (one-pass), early solutions are
        normalized against incomplete bounds and won't hit 0.0/1.0 exactly.
        """
        state = load_state()
        # Objective 0 (latency): min=25 (S11), max=55 (S10)
        # After normalization, S11 should have obj[0]=0.0, S10 should have obj[0]=1.0
        s11 = next(r for r in state if r["solution_id"] == "S11")
        s10 = next(r for r in state if r["solution_id"] == "S10")

        assert abs(s11["normalized_objectives"][0] - 0.0) < 1e-6, (
            f"S11 (min latency=25) should normalize to 0.0 on obj[0], "
            f"got {s11['normalized_objectives'][0]}"
        )
        assert abs(s10["normalized_objectives"][0] - 1.0) < 1e-6, (
            f"S10 (max latency=55) should normalize to 1.0 on obj[0], "
            f"got {s10['normalized_objectives'][0]}"
        )

    def test_aggregate_solutions_properly_normalized(self):
        """AGGREGATE type solutions must be normalized using the same global bounds.

        S16 is AGGREGATE with raw values [45,8200,120,0.94].
        These are the same values as S01 (RAW). After correct two-pass
        normalization using global bounds [25-55, 7000-9600, 75-150, 0.90-0.99],
        both S01 and S16 should get identical normalized values.
        """
        state = load_state()
        s01 = next(r for r in state if r["solution_id"] == "S01")
        s16 = next(r for r in state if r["solution_id"] == "S16")

        for i in range(4):
            assert abs(s01["normalized_objectives"][i] - s16["normalized_objectives"][i]) < 1e-6, (
                f"S01 and S16 have same raw values but different normalized obj[{i}]: "
                f"S01={s01['normalized_objectives'][i]}, S16={s16['normalized_objectives'][i]}. "
                f"AGGREGATE solutions must use the same global bounds as RAW solutions."
            )


# =============================================================================
# TIER 3: Dominance and ranking tests (need Bugs 2+3 fixed)
# =============================================================================

class TestTier3Dominance:
    """Tests that verify correct Pareto dominance and frontier ranking."""

    def test_ranking_not_lexicographic(self):
        """The frontier ranking must NOT be a simple lexicographic sort.

        A correct frontier ranking uses non-dominated sorting: first
        identify the Pareto front (rank 0), remove those, identify the
        next front (rank 1), etc. This differs from sorting by objective
        values because non-dominated solutions can have any objective
        ordering among themselves.
        """
        report = load_report()

        # Lexicographic order would be index-sorted by descending objectives
        ranking = report["frontier_ranking"]
        lex_order = list(range(27))

        assert ranking != lex_order, (
            "Frontier ranking equals index order. This suggests the implementation "
            "is sorting lexicographically instead of computing non-dominated fronts."
        )

    def test_nondominated_pair_count(self):
        """Exactly 331 solution pairs must be identified as mutually non-dominated.

        With 27 solutions there are 351 total pairs.
        Correct analysis: 20 dominance + 331 non-dominated = 351.

        If non-dominated detection only catches solutions with identical
        objectives (instead of mutually non-dominating), the count will be near 0.
        """
        report = load_report()
        assert report["nondominated_count"] == 331, (
            f"Expected exactly 331 non-dominated pairs, got {report['nondominated_count']}. "
            f"Common errors: 0 (checking mutual strict superiority instead of mutual "
            f"non-dominance), or wrong total due to incorrect normalization."
        )

    def test_dominance_asymmetry_and_coverage(self):
        """The dominance relation must be asymmetric AND counts must sum correctly.

        Verifies:
        1. asymmetry_holds is True
        2. dominance_count + nondominated_count = 351 (total pairs)
        3. With 4 objectives and diverse solutions, there MUST be non-dominated pairs
        """
        report = load_report()

        assert report["asymmetry_holds"] is True, (
            "Asymmetry check failed. This indicates incorrect dominance logic."
        )

        total_pairs = 27 * 26 // 2  # 351
        dom = report["dominance_count"]
        nondom = report["nondominated_count"]

        assert dom + nondom == total_pairs, (
            f"Dominance ({dom}) + non-dominated ({nondom}) = {dom + nondom}, "
            f"expected {total_pairs}. Every pair must be classified."
        )

        # With 4 objectives, most solutions trade off differently
        assert nondom >= 200, (
            f"Only {nondom} non-dominated pairs detected. With 4 objectives and "
            f"27 diverse solutions, most pairs should be non-dominated. "
            f"A count near 0 indicates broken non-dominated detection."
        )


# =============================================================================
# TIER 4: Full consistency tests (need ALL bugs fixed)
# =============================================================================

class TestTier4FullConsistency:
    """Tests that require all bugs to be fixed simultaneously."""

    def test_frontier_fingerprint(self):
        """The dominance graph fingerprint must match the expected value.

        This is a SHA-256 hash of the complete dominance structure.
        It depends on:
        - Correct normalization (Bug 1)
        - Correct dominance detection (Bug 2)
        - Correct ranking (Bug 3)
        - Correct fingerprint computation (Bug 4)

        All four bugs must be fixed for this to match.
        """
        report = load_report()
        expected_fingerprint = "8dceef615076ddc9"
        assert report["frontier_fingerprint"] == expected_fingerprint, (
            f"Frontier fingerprint mismatch. Expected '{expected_fingerprint}', "
            f"got '{report['frontier_fingerprint']}'. This hash depends on the "
            f"entire dominance graph being correct."
        )

    def test_full_consistency(self):
        """Cross-validate all metrics for internal consistency.

        Verifies:
        - Exact dominance count (20) and non-dominated count (331)
        - Sum = 351 (total pairs)
        - Ranking is NOT lexicographic
        - Ranking is a valid permutation
        - All normalized values in [0,1]
        """
        report = load_report()
        state = load_state()

        # Exact counts
        assert report["dominance_count"] == 20, (
            f"Expected 20 dominance pairs, got {report['dominance_count']}"
        )
        assert report["nondominated_count"] == 331, (
            f"Expected 331 non-dominated pairs, got {report['nondominated_count']}"
        )

        # Sum check
        n = report["total_solutions"]
        total_pairs = n * (n - 1) // 2
        assert report["dominance_count"] + report["nondominated_count"] == total_pairs

        # Ranking must not be index order
        assert report["frontier_ranking"] != list(range(n))

        # Ranking completeness
        assert sorted(report["frontier_ranking"]) == list(range(n))

        # All normalized values in range
        for record in state:
            for val in record["normalized_objectives"]:
                assert 0.0 <= val <= 1.0
