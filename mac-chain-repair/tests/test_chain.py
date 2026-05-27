"""
Test suite for MAC chain verification system.

14 tests in 4 tiers:
- Tier 1 (6 tests): Structural checks - pass with buggy code
- Tier 2 (3 tests): Chain depth checks - need Bug 1 fixed
- Tier 3 (3 tests): Non-conflicting/verification checks - need Bugs 2+3 fixed
- Tier 4 (2 tests): Full consistency checks - need all bugs fixed
"""

import json
import os
import hashlib

# Output file paths
RUNTIME_DIR = "/app/runtime"
STATE_PATH = os.path.join(RUNTIME_DIR, "chain_state.jsonl")
REPORT_PATH = os.path.join(RUNTIME_DIR, "chain_report.json")


def load_state():
    """Load chain_state.jsonl as a list of dicts."""
    records = []
    with open(STATE_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_report():
    """Load chain_report.json."""
    with open(REPORT_PATH, "r") as f:
        return json.load(f)


# =============================================================================
# TIER 1: Structural tests (pass with buggy code)
# =============================================================================

class TestTier1Structural:
    """Basic structural checks that pass even with buggy chain logic."""

    def test_output_files_exist(self):
        """Both output files must exist after processing."""
        assert os.path.exists(STATE_PATH), f"Missing: {STATE_PATH}"
        assert os.path.exists(REPORT_PATH), f"Missing: {REPORT_PATH}"

    def test_five_authorities_in_output(self):
        """Report must identify exactly 5 authorities."""
        report = load_report()
        assert len(report["authority_ids"]) == 5

    def test_authority_ids_correct(self):
        """Authority IDs must be auth_alpha, auth_beta, auth_delta, auth_epsilon, auth_gamma."""
        report = load_report()
        assert report["authority_ids"] == [
            "auth_alpha", "auth_beta", "auth_delta", "auth_epsilon", "auth_gamma"
        ]

    def test_messages_per_authority(self):
        """Each authority must have the correct event count."""
        report = load_report()
        epa = report["events_per_authority"]
        assert epa["auth_alpha"] == 7, f"auth_alpha expected 7, got {epa['auth_alpha']}"
        assert epa["auth_beta"] == 6, f"auth_beta expected 6, got {epa['auth_beta']}"
        assert epa["auth_gamma"] == 6, f"auth_gamma expected 6, got {epa['auth_gamma']}"
        assert epa["auth_delta"] == 6, f"auth_delta expected 6, got {epa['auth_delta']}"
        assert epa["auth_epsilon"] == 5, f"auth_epsilon expected 5, got {epa['auth_epsilon']}"

    def test_report_has_required_fields(self):
        """Report must contain all required fields."""
        report = load_report()
        required = [
            "authority_ids", "total_events", "events_per_authority",
            "conflict_count", "non_conflicting_count", "verification_order",
            "asymmetry_holds", "chain_fingerprint"
        ]
        for field in required:
            assert field in report, f"Missing field: {field}"

    def test_total_messages_count(self):
        """Total event count must be 30."""
        report = load_report()
        assert report["total_events"] == 30
        state = load_state()
        assert len(state) == 30


# =============================================================================
# TIER 2: Chain depth tests (need Bug 1 fixed - SYNC must advance chain)
# =============================================================================

class TestTier2ChainValues:
    """Tests that verify correct chain depth computation on SYNC."""

    def test_chain_depth_after_sync(self):
        """After auth_beta receives s01, its own chain depth must be advanced.

        auth_beta starts with depth [alpha:0, beta:9, delta:0, epsilon:0, gamma:0]
        (after its first SIGN consumed 1 from initial 10).
        auth_beta receives s01 with peer_chain [alpha:7, beta:0, gamma:0, delta:0, epsilon:0].
        Correct merge: max([0,9,0,0,0], [7,0,0,0,0]) = [7,9,0,0,0], then +1 on beta = [7,10,0,0,0].

        If the SYNC advancement is missing, auth_beta would be [7,9,0,0,0] instead.
        """
        state = load_state()
        # Find auth_beta's SYNC event for s01 (timestamp 300)
        sync_event = None
        for record in state:
            if (record["authority"] == "auth_beta" and
                record["msg_type"] == "SYNC" and
                record["timestamp"] == 300):
                sync_event = record
                break

        assert sync_event is not None, "Could not find auth_beta SYNC event at ts=300"
        depth = sync_event["chain_depth"]
        assert depth["auth_beta"] == 10, (
            f"After SYNC+merge, auth_beta's own depth should be 10 (merge then advance). "
            f"Got auth_beta={depth['auth_beta']}. If auth_beta=9, the post-merge advancement is missing."
        )
        assert depth["auth_alpha"] == 7, f"auth_beta should have auth_alpha=7 after merge. Got {depth['auth_alpha']}"

    def test_chain_state_dominance(self):
        """After SYNC, the receiver's chain state must strictly dominate the peer's state.

        auth_alpha receives s05 at ts=1050. Peer state is [alpha:7, beta:8, gamma:5, delta:4, epsilon:7].
        auth_alpha's depth before this SYNC is [alpha:1, beta:0, delta:0, epsilon:0, gamma:0].

        Correct: merge gives [7,8,5,4,7], then advance alpha -> [8,8,5,4,7].
        This strictly dominates [7,8,5,4,7] because alpha:8 > 7.

        If advancement is missing: merge gives [7,8,5,4,7] which EQUALS peer state.
        Equal does NOT satisfy strict dominance (all >= but not any >).
        """
        state = load_state()

        # Check auth_alpha's SYNC s05 (ts=1050)
        sync_event = None
        for record in state:
            if (record["authority"] == "auth_alpha" and
                record["msg_type"] == "SYNC" and
                record["timestamp"] == 1050):
                sync_event = record
                break

        assert sync_event is not None, "Could not find auth_alpha SYNC event at ts=1050"
        depth = sync_event["chain_depth"]
        peer_state = {"auth_alpha": 7, "auth_beta": 8, "auth_gamma": 5, "auth_delta": 4, "auth_epsilon": 7}

        # Receiver must dominate: all >= AND at least one >
        for auth in peer_state:
            assert depth[auth] >= peer_state[auth], (
                f"Receiver depth must be >= peer for all components. "
                f"{auth}: receiver={depth[auth]} < peer={peer_state[auth]}"
            )

        assert any(depth[a] > peer_state[a] for a in peer_state), (
            f"Receiver depth must strictly dominate peer state (at least one component >). "
            f"Got receiver={depth}, peer={peer_state}. "
            f"If they're equal, the post-merge advancement on the receiver's own component is missing."
        )

    def test_final_chain_values(self):
        """Each authority's final own-depth must reflect all events processed.

        svc_alpha: 7 events, final own=7 (from last SYNC merge+advance then subsequent SIGN)
        svc_beta: 6 events, final own=9 (from last SYNC s06 merge+advance then nothing more consumed)
        svc_gamma: 6 events, final own=2
        """
        state = load_state()
        # Find each authority's last event
        last_by_authority = {}
        for record in state:
            last_by_authority[record["authority"]] = record

        assert last_by_authority["auth_alpha"]["chain_depth"]["auth_alpha"] == 7, (
            f"auth_alpha's final own-depth should be 7. "
            f"Got {last_by_authority['auth_alpha']['chain_depth']['auth_alpha']}"
        )
        assert last_by_authority["auth_beta"]["chain_depth"]["auth_beta"] == 9, (
            f"auth_beta's final own-depth should be 9. "
            f"Got {last_by_authority['auth_beta']['chain_depth']['auth_beta']}"
        )
        assert last_by_authority["auth_gamma"]["chain_depth"]["auth_gamma"] == 2, (
            f"auth_gamma's final own-depth should be 2. "
            f"Got {last_by_authority['auth_gamma']['chain_depth']['auth_gamma']}"
        )


# =============================================================================
# TIER 3: Non-conflicting and verification tests (need Bugs 2+3 fixed)
# =============================================================================

class TestTier3VerificationOrdering:
    """Tests that verify correct non-conflicting detection and verification order."""

    def test_ordering_not_timestamp_based(self):
        """The verification order must NOT be a simple timestamp sort.

        A correct verification order uses priority-based topological sort
        of the conflict DAG. Since non-conflicting events can be ordered freely,
        the correct topological sort (using chain-sum tiebreaking) differs from
        pure timestamp ordering.

        The timestamp-sorted order would be [0,1,2,3,...,29] since events
        are indexed by ascending timestamp. A correct priority-based sort
        reorders non-conflicting events based on chain depth priority.
        """
        report = load_report()

        # Timestamp order is just [0, 1, 2, ..., 29]
        timestamp_order = list(range(30))
        verification_order = report["verification_order"]

        assert verification_order != timestamp_order, (
            "Verification order equals timestamp order. This suggests the implementation "
            "is sorting by physical timestamp instead of computing a priority-based "
            "topological sort of the conflict partial order. Physical time != verification "
            "priority in MAC chain systems."
        )

    def test_non_conflicting_pair_count(self):
        """Exactly 219 event pairs must be identified as non-conflicting.

        With 30 events there are 435 total pairs.
        Correct analysis: 216 conflict + 219 non-conflicting = 435.

        If non-conflicting detection only catches equal chain states (instead of
        mutually non-dominating states), the count will be near 0.
        """
        report = load_report()
        assert report["non_conflicting_count"] == 219, (
            f"Expected exactly 219 non-conflicting pairs, got {report['non_conflicting_count']}. "
            f"Common errors: 0 (checking chain equality instead of mutual non-dominance), "
            f"or wrong total due to incorrect chain values from missing SYNC advancement."
        )

    def test_conflict_coverage_and_asymmetry(self):
        """The conflict relation must be asymmetric AND the counts must sum correctly.

        Verifies:
        1. asymmetry_holds is True
        2. conflict_count + non_conflicting_count = 435 (total pairs)
        3. The non-conflicting count doesn't fall below the theoretical minimum
           for a 30-event trace with 5 authorities
        """
        report = load_report()

        assert report["asymmetry_holds"] is True, (
            "Asymmetry check failed. This indicates either incorrect chain "
            "depth values or a bug in conflict detection."
        )

        total_pairs = 30 * 29 // 2  # 435
        conflicts = report["conflict_count"]
        non_conflicting = report["non_conflicting_count"]

        assert conflicts + non_conflicting == total_pairs, (
            f"Conflicts ({conflicts}) + non-conflicting ({non_conflicting}) = {conflicts + non_conflicting}, "
            f"expected {total_pairs}. Every pair must be classified as either conflict or non-conflicting."
        )

        # With 5 authorities and varied chain evolution, there MUST be non-conflicting pairs
        assert non_conflicting >= 100, (
            f"Only {non_conflicting} non-conflicting pairs detected. With 5 authorities and varied "
            f"chain evolution, many event pairs must have incomparable chain states. "
            f"A count near 0 indicates broken non-conflicting detection."
        )


# =============================================================================
# TIER 4: Full consistency tests (need ALL bugs fixed)
# =============================================================================

class TestTier4FullConsistency:
    """Tests that require all bugs to be fixed simultaneously."""

    def test_chain_fingerprint(self):
        """The verification graph fingerprint must match the expected value.

        This is a SHA-256 hash of the complete verification graph structure.
        It depends on:
        - Correct chain depth values (Bug 1)
        - Correct non-conflicting detection (Bug 2)
        - Correct conflict classification (Bug 3)
        - Correct fingerprint computation (Bug 4)

        All four bugs must be fixed for this to match.
        """
        report = load_report()
        expected_fingerprint = "6f9956d27e6bec87"
        assert report["chain_fingerprint"] == expected_fingerprint, (
            f"Chain fingerprint mismatch. Expected '{expected_fingerprint}', "
            f"got '{report['chain_fingerprint']}'. This hash depends on the entire "
            f"verification graph being correct."
        )

    def test_full_consistency(self):
        """Cross-validate all metrics for internal consistency.

        Verifies:
        - Exact conflict count (216) and non-conflicting count (219)
        - conflict + non-conflicting = 435 (total pairs)
        - Verification order is NOT timestamp order
        - Verification order is a valid permutation
        - Chain depth values at final events are correct

        This test requires all bugs to be fixed because it checks
        exact counts (need Bug 1 + Bug 2), ordering (need Bug 3),
        and final chain values (need Bug 1).
        """
        report = load_report()
        state = load_state()

        # Exact counts check (needs Bug 1 for correct depths + Bug 2 for correct classification)
        assert report["conflict_count"] == 216, (
            f"Expected 216 conflict pairs, got {report['conflict_count']}"
        )
        assert report["non_conflicting_count"] == 219, (
            f"Expected 219 non-conflicting pairs, got {report['non_conflicting_count']}"
        )

        # Sum check
        n = report["total_events"]
        total_pairs = n * (n - 1) // 2
        conflicts = report["conflict_count"]
        non_conflicting = report["non_conflicting_count"]
        assert conflicts + non_conflicting == total_pairs, (
            f"Conflicts ({conflicts}) + non-conflicting ({non_conflicting}) = {conflicts + non_conflicting}, "
            f"expected {total_pairs}"
        )

        # Verification order must not be timestamp order (needs Bug 3 fixed)
        timestamp_order = list(range(n))
        assert report["verification_order"] != timestamp_order, (
            "Verification order should differ from timestamp order"
        )

        # Verification order completeness
        assert sorted(report["verification_order"]) == list(range(n)), (
            "Verification order must be a permutation of all event indices"
        )

        # Final chain depth values (needs Bug 1 for correct advancement cascade)
        last_alpha = None
        for record in reversed(state):
            if record["authority"] == "auth_alpha":
                last_alpha = record
                break
        assert last_alpha is not None
        assert last_alpha["chain_depth"]["auth_alpha"] == 7, (
            f"auth_alpha's final depth should be 7, got {last_alpha['chain_depth']['auth_alpha']}"
        )

        last_beta = None
        for record in reversed(state):
            if record["authority"] == "auth_beta":
                last_beta = record
                break
        assert last_beta is not None
        assert last_beta["chain_depth"]["auth_beta"] == 9, (
            f"auth_beta's final depth should be 9, got {last_beta['chain_depth']['auth_beta']}"
        )

        last_delta = None
        for record in reversed(state):
            if record["authority"] == "auth_delta":
                last_delta = record
                break
        assert last_delta is not None
        assert last_delta["chain_depth"]["auth_delta"] == 0, (
            f"auth_delta's final depth should be 0, got {last_delta['chain_depth']['auth_delta']}"
        )
