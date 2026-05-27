"""
Test suite for TCP-like flow control window management system.

14 tests in 4 tiers:
- Tier 1 (6 tests): Structural checks - pass with buggy code
- Tier 2 (3 tests): Window value checks - need Bug 1 fixed
- Tier 3 (3 tests): Contention-free/scheduling checks - need Bugs 2+3 fixed
- Tier 4 (2 tests): Full consistency checks - need all bugs fixed
"""

import json
import os
import hashlib

# Output file paths
RUNTIME_DIR = "/app/runtime"
STATE_PATH = os.path.join(RUNTIME_DIR, "congestion_state.jsonl")
REPORT_PATH = os.path.join(RUNTIME_DIR, "congestion_report.json")


def load_state():
    """Load congestion_state.jsonl as a list of dicts."""
    records = []
    with open(STATE_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_report():
    """Load congestion_report.json."""
    with open(REPORT_PATH, "r") as f:
        return json.load(f)


# =============================================================================
# TIER 1: Structural tests (pass with buggy code)
# =============================================================================

class TestTier1Structural:
    """Basic structural checks that pass even with buggy window logic."""

    def test_output_files_exist(self):
        """Both output files must exist after processing."""
        assert os.path.exists(STATE_PATH), f"Missing: {STATE_PATH}"
        assert os.path.exists(REPORT_PATH), f"Missing: {REPORT_PATH}"

    def test_five_connections_in_output(self):
        """Report must identify exactly 5 connections."""
        report = load_report()
        assert len(report["connection_ids"]) == 5

    def test_connection_ids_correct(self):
        """Connection IDs must be conn_alpha, conn_beta, conn_delta, conn_epsilon, conn_gamma."""
        report = load_report()
        assert report["connection_ids"] == [
            "conn_alpha", "conn_beta", "conn_delta", "conn_epsilon", "conn_gamma"
        ]

    def test_packets_per_connection(self):
        """Each connection must have the correct packet count."""
        report = load_report()
        ppc = report["packets_per_connection"]
        assert ppc["conn_alpha"] == 7, f"conn_alpha expected 7, got {ppc['conn_alpha']}"
        assert ppc["conn_beta"] == 6, f"conn_beta expected 6, got {ppc['conn_beta']}"
        assert ppc["conn_gamma"] == 6, f"conn_gamma expected 6, got {ppc['conn_gamma']}"
        assert ppc["conn_delta"] == 6, f"conn_delta expected 6, got {ppc['conn_delta']}"
        assert ppc["conn_epsilon"] == 5, f"conn_epsilon expected 5, got {ppc['conn_epsilon']}"

    def test_report_has_required_fields(self):
        """Report must contain all required fields."""
        report = load_report()
        required = [
            "connection_ids", "total_packets", "packets_per_connection",
            "competing_count", "contention_free_count", "scheduling_order",
            "asymmetry_holds", "congestion_fingerprint"
        ]
        for field in required:
            assert field in report, f"Missing field: {field}"

    def test_total_packets_count(self):
        """Total packet count must be 30."""
        report = load_report()
        assert report["total_packets"] == 30
        state = load_state()
        assert len(state) == 30


# =============================================================================
# TIER 2: Window value tests (need Bug 1 fixed - SACK must advance window)
# =============================================================================

class TestTier2WindowValues:
    """Tests that verify correct congestion window computation on SACK."""

    def test_window_after_sack(self):
        """After conn_beta receives s01, its own window must be advanced.

        conn_beta starts with window [alpha:0, beta:9, delta:0, epsilon:0, gamma:0]
        (after its first DATA consumed 1 from initial 10).
        conn_beta receives s01 with peer_window [alpha:7, beta:0, gamma:0, delta:0, epsilon:0].
        Correct merge: max([0,9,0,0,0], [7,0,0,0,0]) = [7,9,0,0,0], then +1 on beta = [7,10,0,0,0].

        If the SACK advancement is missing, conn_beta would be [7,9,0,0,0] instead.
        """
        state = load_state()
        # Find conn_beta's SACK event for s01 (timestamp 300)
        sack_event = None
        for record in state:
            if (record["connection"] == "conn_beta" and
                record["ack_type"] == "SACK" and
                record["timestamp"] == 300):
                sack_event = record
                break

        assert sack_event is not None, "Could not find conn_beta SACK event at ts=300"
        window = sack_event["congestion_window"]
        assert window["conn_beta"] == 10, (
            f"After SACK+merge, conn_beta's own window should be 10 (merge then advance). "
            f"Got conn_beta={window['conn_beta']}. If conn_beta=9, the post-merge advancement is missing."
        )
        assert window["conn_alpha"] == 7, f"conn_beta should have conn_alpha=7 after merge. Got {window['conn_alpha']}"

    def test_window_dominance(self):
        """After SACK, the receiver's window must strictly dominate the sender's state.

        conn_alpha receives s05 at ts=1050. Sender state is [alpha:7, beta:8, gamma:5, delta:4, epsilon:7].
        conn_alpha's window before this SACK is [alpha:1, beta:0, delta:0, epsilon:0, gamma:0].

        Correct: merge gives [7,8,5,4,7], then advance alpha -> [8,8,5,4,7].
        This strictly dominates [7,8,5,4,7] because alpha:8 > 7.

        If advancement is missing: merge gives [7,8,5,4,7] which EQUALS sender state.
        Equal does NOT satisfy strict dominance (all >= but not any >).
        """
        state = load_state()

        # Check conn_alpha's SACK s05 (ts=1050)
        sack_event = None
        for record in state:
            if (record["connection"] == "conn_alpha" and
                record["ack_type"] == "SACK" and
                record["timestamp"] == 1050):
                sack_event = record
                break

        assert sack_event is not None, "Could not find conn_alpha SACK event at ts=1050"
        window = sack_event["congestion_window"]
        sender_state = {"conn_alpha": 7, "conn_beta": 8, "conn_gamma": 5, "conn_delta": 4, "conn_epsilon": 7}

        # Receiver must dominate: all >= AND at least one >
        for conn in sender_state:
            assert window[conn] >= sender_state[conn], (
                f"Receiver window must be >= sender for all components. "
                f"{conn}: receiver={window[conn]} < sender={sender_state[conn]}"
            )

        assert any(window[c] > sender_state[c] for c in sender_state), (
            f"Receiver window must strictly dominate sender state (at least one component >). "
            f"Got receiver={window}, sender={sender_state}. "
            f"If they're equal, the post-merge advancement on the receiver's own component is missing."
        )

    def test_final_window_values(self):
        """Each connection's final own-window must reflect all events processed.

        conn_alpha: 7 events (3 DATA cost=1 each + 2 DUPLEX cost=3 each + 1 DATA cost=1 + 1 SACK)
          Initial=10, consume: -1-3-1-3-1-1 = -10, SACK merge gives higher then +1 = final own=7
        conn_beta: 6 events, final own=9 (from last SACK s06 merge+advance)

        The final own-window for conn_alpha should be 7 and conn_beta should be 9.
        """
        state = load_state()
        # Find each connection's last event
        last_by_connection = {}
        for record in state:
            last_by_connection[record["connection"]] = record

        assert last_by_connection["conn_alpha"]["congestion_window"]["conn_alpha"] == 7, (
            f"conn_alpha's final own-window should be 7. "
            f"Got {last_by_connection['conn_alpha']['congestion_window']['conn_alpha']}"
        )
        assert last_by_connection["conn_beta"]["congestion_window"]["conn_beta"] == 9, (
            f"conn_beta's final own-window should be 9. "
            f"Got {last_by_connection['conn_beta']['congestion_window']['conn_beta']}"
        )
        assert last_by_connection["conn_gamma"]["congestion_window"]["conn_gamma"] == 2, (
            f"conn_gamma's final own-window should be 2. "
            f"Got {last_by_connection['conn_gamma']['congestion_window']['conn_gamma']}"
        )


# =============================================================================
# TIER 3: Contention-free and scheduling tests (need Bugs 2+3 fixed)
# =============================================================================

class TestTier3CongestionOrdering:
    """Tests that verify correct contention-free detection and scheduling order."""

    def test_scheduling_not_timestamp_based(self):
        """The scheduling order must NOT be a simple timestamp sort.

        A correct scheduling order uses priority-based topological sort
        of the competing DAG. Since contention-free packets can be ordered freely,
        the correct topological sort (using window-sum tiebreaking) differs from
        pure timestamp ordering.

        The timestamp-sorted order would be [0,1,2,3,...,29] since packets
        are indexed by ascending timestamp. A correct priority-based sort
        reorders contention-free packets based on window priority.
        """
        report = load_report()

        # Timestamp order is just [0, 1, 2, ..., 29]
        timestamp_order = list(range(30))
        scheduling_order = report["scheduling_order"]

        assert scheduling_order != timestamp_order, (
            "Scheduling order equals timestamp order. This suggests the implementation "
            "is sorting by physical ACK arrival time instead of computing a priority-based "
            "topological sort of the competing partial order. Physical time != scheduling "
            "priority in flow-controlled systems."
        )

    def test_contention_free_pair_count(self):
        """Exactly 219 packet pairs must be identified as contention-free.

        With 30 packets there are 435 total pairs.
        Correct analysis: 216 competing + 219 contention-free = 435.

        If contention-free detection only catches equal windows (instead of
        mutually non-dominating windows), the count will be near 0.
        """
        report = load_report()
        assert report["contention_free_count"] == 219, (
            f"Expected exactly 219 contention-free pairs, got {report['contention_free_count']}. "
            f"Common errors: 0 (checking window equality instead of mutual non-dominance), "
            f"or wrong total due to incorrect window values from missing advancement."
        )

    def test_competing_coverage_and_asymmetry(self):
        """The competing relation must be asymmetric AND the counts must sum correctly.

        Verifies:
        1. asymmetry_holds is True
        2. competing_count + contention_free_count = 435 (total pairs)
        3. The contention-free count doesn't fall below the theoretical minimum
           for a 30-packet trace with 5 connections
        """
        report = load_report()

        assert report["asymmetry_holds"] is True, (
            "Asymmetry check failed. This indicates either incorrect congestion "
            "window values or a bug in competing detection."
        )

        total_pairs = 30 * 29 // 2  # 435
        competing = report["competing_count"]
        contention_free = report["contention_free_count"]

        assert competing + contention_free == total_pairs, (
            f"Competing ({competing}) + contention-free ({contention_free}) = {competing + contention_free}, "
            f"expected {total_pairs}. Every pair must be classified as either competing or contention-free."
        )

        # With 5 connections and varied window evolution, there MUST be contention-free pairs
        assert contention_free >= 100, (
            f"Only {contention_free} contention-free pairs detected. With 5 connections and varied "
            f"window evolution, many packet pairs must have incomparable windows. "
            f"A count near 0 indicates broken contention-free detection."
        )


# =============================================================================
# TIER 4: Full consistency tests (need ALL bugs fixed)
# =============================================================================

class TestTier4FullConsistency:
    """Tests that require all bugs to be fixed simultaneously."""

    def test_congestion_fingerprint(self):
        """The congestion graph fingerprint must match the expected value.

        This is a SHA-256 hash of the complete scheduling graph structure.
        It depends on:
        - Correct congestion window values (Bug 1)
        - Correct contention-free detection (Bug 2)
        - Correct competing classification (Bug 3)
        - Correct fingerprint computation (Bug 4)

        All four bugs must be fixed for this to match.
        """
        report = load_report()
        expected_fingerprint = "fd5712752da9f511"
        assert report["congestion_fingerprint"] == expected_fingerprint, (
            f"Congestion fingerprint mismatch. Expected '{expected_fingerprint}', "
            f"got '{report['congestion_fingerprint']}'. This hash depends on the entire "
            f"scheduling graph being correct."
        )

    def test_full_consistency(self):
        """Cross-validate all metrics for internal consistency.

        Verifies:
        - Exact competing count (216) and contention-free count (219)
        - competing + contention-free = 435 (total pairs)
        - Scheduling order is NOT timestamp order
        - Scheduling order is a valid permutation
        - Window values at final packets are correct

        This test requires all bugs to be fixed because it checks
        exact counts (need Bug 1 + Bug 2), ordering (need Bug 3),
        and final window values (need Bug 1).
        """
        report = load_report()
        state = load_state()

        # Exact counts check (needs Bug 1 for correct windows + Bug 2 for correct classification)
        assert report["competing_count"] == 216, (
            f"Expected 216 competing pairs, got {report['competing_count']}"
        )
        assert report["contention_free_count"] == 219, (
            f"Expected 219 contention-free pairs, got {report['contention_free_count']}"
        )

        # Sum check
        n = report["total_packets"]
        total_pairs = n * (n - 1) // 2
        competing = report["competing_count"]
        contention_free = report["contention_free_count"]
        assert competing + contention_free == total_pairs, (
            f"Competing ({competing}) + contention-free ({contention_free}) = {competing + contention_free}, "
            f"expected {total_pairs}"
        )

        # Scheduling order must not be timestamp order (needs Bug 3 fixed)
        timestamp_order = list(range(n))
        assert report["scheduling_order"] != timestamp_order, (
            "Scheduling order should differ from timestamp order"
        )

        # Scheduling order completeness
        assert sorted(report["scheduling_order"]) == list(range(n)), (
            "Scheduling order must be a permutation of all packet indices"
        )

        # Final window values (needs Bug 1 for correct advancement cascade)
        last_alpha = None
        for record in reversed(state):
            if record["connection"] == "conn_alpha":
                last_alpha = record
                break
        assert last_alpha is not None
        assert last_alpha["congestion_window"]["conn_alpha"] == 7, (
            f"conn_alpha's final window should be 7, got {last_alpha['congestion_window']['conn_alpha']}"
        )

        last_beta = None
        for record in reversed(state):
            if record["connection"] == "conn_beta":
                last_beta = record
                break
        assert last_beta is not None
        assert last_beta["congestion_window"]["conn_beta"] == 9, (
            f"conn_beta's final window should be 9, got {last_beta['congestion_window']['conn_beta']}"
        )

        last_delta = None
        for record in reversed(state):
            if record["connection"] == "conn_delta":
                last_delta = record
                break
        assert last_delta is not None
        assert last_delta["congestion_window"]["conn_delta"] == 0, (
            f"conn_delta's final window should be 0, got {last_delta['congestion_window']['conn_delta']}"
        )
