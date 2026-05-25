"""
Tests for the product lattice information flow analysis system.

Validates correctness of the two-dimensional security lattice operations
including dominance detection, violation classification, combined label
computation, event deduplication, and volume aggregation.
"""

import json
import os


OUTPUT_DIR = "/app/runtime/output"


class TestOutputStructure:
    """Verify that the analysis produces well-formed output files."""

    def test_summary_file_exists(self):
        """The analysis must produce a summary.json report file."""
        path = os.path.join(OUTPUT_DIR, "summary.json")
        assert os.path.exists(path), (
            f"Expected summary report at {path}."
        )

    def test_violations_file_exists(self):
        """The analysis must produce a violations.json report file."""
        path = os.path.join(OUTPUT_DIR, "violations.json")
        assert os.path.exists(path), (
            f"Expected violations report at {path}."
        )

    def test_flow_matrix_file_exists(self):
        """The analysis must produce a flow_matrix.json report file."""
        path = os.path.join(OUTPUT_DIR, "flow_matrix.json")
        assert os.path.exists(path), (
            f"Expected flow matrix at {path}."
        )

    def test_summary_has_required_fields(self):
        """Summary must contain all required statistical fields."""
        path = os.path.join(OUTPUT_DIR, "summary.json")
        with open(path) as f:
            summary = json.load(f)
        required = [
            "total_events_loaded",
            "events_after_dedup",
            "total_violations",
            "source_volumes",
            "flow_matrix_size"
        ]
        for field in required:
            assert field in summary, (
                f"Missing field '{field}' in summary.json"
            )

    def test_total_events_loaded(self):
        """All 54 events from three source files must be loaded."""
        path = os.path.join(OUTPUT_DIR, "summary.json")
        with open(path) as f:
            summary = json.load(f)
        assert summary["total_events_loaded"] == 54, (
            f"Expected 54 total events, got {summary['total_events_loaded']}"
        )


class TestDeduplication:
    """Verify correct event deduplication semantics."""

    def test_dedup_preserves_cross_source_events(self):
        """Events from different sources referencing the same entity must be preserved.

        When multiple independent sources report flows involving the same entity
        within the deduplication window, these represent genuinely distinct
        information flows from different organizational units. The deduplication
        policy must preserve source-level autonomy by including the source
        identity in the deduplication key.
        """
        path = os.path.join(OUTPUT_DIR, "summary.json")
        with open(path) as f:
            summary = json.load(f)
        # All 54 events are distinct (different source_id for same-entity pairs)
        assert summary["events_after_dedup"] == 54, (
            f"Expected 54 events after deduplication (no true duplicates exist), "
            f"got {summary['events_after_dedup']}. "
            "Verify that the deduplication identity includes the source stream "
            "in /app/runtime/loader.py — events from different sources for the "
            "same entity are independent observations, not duplicates."
        )

    def test_research_volume_includes_all_events(self):
        """Research source volume must include all 18 research events.

        If cross-source deduplication incorrectly merges events from different
        sources, the research volume will be lower than expected because some
        research events sharing entity names with engineering events would be
        dropped.
        """
        path = os.path.join(OUTPUT_DIR, "summary.json")
        with open(path) as f:
            summary = json.load(f)
        # Research has 18 events totaling volume 328
        assert summary["source_volumes"]["research"] == 328, (
            f"Expected research volume 328, got {summary['source_volumes'].get('research')}. "
            "Check whether the deduplication in /app/runtime/loader.py incorrectly "
            "merges events from different source streams that share an entity name."
        )


class TestDominanceDetection:
    """Verify product lattice dominance uses componentwise ordering."""

    def test_violation_count_reflects_componentwise_dominance(self):
        """Only flows where BOTH dimensions increase should be classified as violations.

        In a product lattice C x I, element (c1,i1) is dominated by (c2,i2)
        only when c1 <= c2 AND i1 <= i2 (with at least one strict). Flows where
        one dimension increases while the other decreases are INCOMPARABLE
        in the partial order and must not be classified as upward flows.

        With the test data and a distance threshold of 2, there are exactly
        9 true violations under the componentwise partial order.
        """
        path = os.path.join(OUTPUT_DIR, "violations.json")
        with open(path) as f:
            report = json.load(f)
        assert report["violation_count"] == 9, (
            f"Expected 9 violations under componentwise product lattice ordering, "
            f"got {report['violation_count']}. "
            "The product lattice partial order requires BOTH dimensions to be "
            "non-decreasing (and at least one strictly increasing) for dominance. "
            "Check the dominance predicate in /app/runtime/lattice.py — it must "
            "compare each dimension independently, not reduce to a scalar."
        )

    def test_incomparable_flows_excluded(self):
        """Flows where conf increases but integ decreases must NOT appear as violations.

        Event eng-004 flows from (internal, certified) to (secret, verified).
        Confidentiality increases (rank 1->3) but integrity DECREASES (rank 3->2).
        These labels are incomparable in the product lattice and the flow must
        not be flagged as a violation.
        """
        path = os.path.join(OUTPUT_DIR, "violations.json")
        with open(path) as f:
            report = json.load(f)
        violation_ids = {v["event_id"] for v in report["violations"]}
        assert "eng-004" not in violation_ids, (
            "Event eng-004 should NOT be a violation. It flows from "
            "(internal, certified) to (secret, verified) — confidentiality increases "
            "but integrity DECREASES. These are incomparable elements in the "
            "product lattice. Check dominance logic in /app/runtime/lattice.py."
        )
        assert "eng-006" not in violation_ids, (
            "Event eng-006 should NOT be a violation. It flows from "
            "(internal, authoritative) to (top_secret, verified) — incomparable "
            "elements where confidentiality increases but integrity decreases."
        )


class TestDistanceMetric:
    """Verify product lattice distance uses correct metric."""

    def test_violation_distance_uses_chebyshev(self):
        """Lattice distance must be the maximum dimensional change (L-infinity norm).

        In a product lattice, the distance between two elements measures the
        worst-case dimensional displacement. For security analysis, a flow
        crossing 3 levels in confidentiality but 1 level in integrity has
        distance 3 (the maximum), not 4 (the sum).

        Event cmp-002 flows from (confidential=2, provisional=1) to
        (secret=3, authoritative=4): conf_delta=1, integ_delta=3.
        The correct distance is max(1,3) = 3, not 1+3 = 4.
        """
        path = os.path.join(OUTPUT_DIR, "violations.json")
        with open(path) as f:
            report = json.load(f)
        cmp002 = None
        for v in report["violations"]:
            if v["event_id"] == "cmp-002":
                cmp002 = v
                break
        assert cmp002 is not None, (
            "Expected cmp-002 to be a violation"
        )
        assert cmp002["distance"] == 3, (
            f"Distance for cmp-002 should be 3 (max of dimensional deltas), "
            f"got {cmp002['distance']}. The product lattice distance is the "
            "L-infinity (Chebyshev) distance: max(|conf_delta|, |integ_delta|). "
            "Check flow_distance() in /app/runtime/lattice.py."
        )


class TestJoinComputation:
    """Verify the product lattice join produces componentwise maximum."""

    def test_combined_label_is_componentwise_max(self):
        """The join must take the maximum of each dimension independently.

        For event res-003 flowing from (internal, untrusted) to (secret, certified):
        - The join of these two elements is (max(internal,secret), max(untrusted,certified))
        - Which equals (secret, certified)

        The join in a product lattice is NOT the average or midpoint — it is
        the componentwise maximum, representing the least upper bound that
        dominates both input elements.
        """
        path = os.path.join(OUTPUT_DIR, "violations.json")
        with open(path) as f:
            report = json.load(f)
        res003 = None
        for v in report["violations"]:
            if v["event_id"] == "res-003":
                res003 = v
                break
        assert res003 is not None, (
            "Expected res-003 to be a violation"
        )
        assert res003["combined_conf"] == "secret", (
            f"Combined confidentiality for res-003 should be 'secret' "
            f"(max of 'internal' and 'secret'), got '{res003['combined_conf']}'. "
            "The join in a product lattice computes the componentwise maximum. "
            "Check join() in /app/runtime/lattice.py."
        )
        assert res003["combined_integ"] == "certified", (
            f"Combined integrity for res-003 should be 'certified' "
            f"(max of 'untrusted' and 'certified'), got '{res003['combined_integ']}'. "
            "Check join() in /app/runtime/lattice.py."
        )

    def test_combined_label_for_high_severity_flow(self):
        """The join of (public, untrusted) and (top_secret, authoritative) is (top_secret, authoritative).

        Event cmp-004 represents the highest-severity flow. Its combined
        classification must be the componentwise maximum of both endpoints.
        """
        path = os.path.join(OUTPUT_DIR, "violations.json")
        with open(path) as f:
            report = json.load(f)
        cmp004 = None
        for v in report["violations"]:
            if v["event_id"] == "cmp-004":
                cmp004 = v
                break
        assert cmp004 is not None, (
            "Expected cmp-004 to be a violation"
        )
        assert cmp004["combined_conf"] == "top_secret", (
            f"Combined conf for cmp-004 should be 'top_secret', "
            f"got '{cmp004['combined_conf']}'"
        )
        assert cmp004["combined_integ"] == "authoritative", (
            f"Combined integ for cmp-004 should be 'authoritative', "
            f"got '{cmp004['combined_integ']}'"
        )
