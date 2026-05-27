"""
Test suite for sliding window rate limiter system.

14 tests in 4 tiers:
- Tier 1 (6 tests): Structural checks - pass with buggy code
- Tier 2 (3 tests): Token budget checks - need Bug 1 fixed
- Tier 3 (3 tests): Independence/scheduling checks - need Bugs 2+3 fixed
- Tier 4 (2 tests): Full consistency checks - need all bugs fixed
"""

import json
import os
import hashlib

# Output file paths
RUNTIME_DIR = "/app/runtime"
STATE_PATH = os.path.join(RUNTIME_DIR, "throttle_state.jsonl")
REPORT_PATH = os.path.join(RUNTIME_DIR, "throttle_report.json")


def load_state():
    """Load throttle_state.jsonl as a list of dicts."""
    records = []
    with open(STATE_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_report():
    """Load throttle_report.json."""
    with open(REPORT_PATH, "r") as f:
        return json.load(f)


# =============================================================================
# TIER 1: Structural tests (pass with buggy code)
# =============================================================================

class TestTier1Structural:
    """Basic structural checks that pass even with buggy token logic."""

    def test_output_files_exist(self):
        """Both output files must exist after processing."""
        assert os.path.exists(STATE_PATH), f"Missing: {STATE_PATH}"
        assert os.path.exists(REPORT_PATH), f"Missing: {REPORT_PATH}"

    def test_five_services_in_output(self):
        """Report must identify exactly 5 services."""
        report = load_report()
        assert len(report["service_ids"]) == 5

    def test_service_ids_correct(self):
        """Service IDs must be svc_alpha, svc_beta, svc_delta, svc_epsilon, svc_gamma."""
        report = load_report()
        assert report["service_ids"] == [
            "svc_alpha", "svc_beta", "svc_delta", "svc_epsilon", "svc_gamma"
        ]

    def test_requests_per_service(self):
        """Each service must have the correct request count."""
        report = load_report()
        rps = report["requests_per_service"]
        assert rps["svc_alpha"] == 7, f"svc_alpha expected 7, got {rps['svc_alpha']}"
        assert rps["svc_beta"] == 6, f"svc_beta expected 6, got {rps['svc_beta']}"
        assert rps["svc_gamma"] == 6, f"svc_gamma expected 6, got {rps['svc_gamma']}"
        assert rps["svc_delta"] == 6, f"svc_delta expected 6, got {rps['svc_delta']}"
        assert rps["svc_epsilon"] == 5, f"svc_epsilon expected 5, got {rps['svc_epsilon']}"

    def test_report_has_required_fields(self):
        """Report must contain all required fields."""
        report = load_report()
        required = [
            "service_ids", "total_requests", "requests_per_service",
            "conflict_count", "independent_count", "scheduling_order",
            "asymmetry_holds", "throttle_fingerprint"
        ]
        for field in required:
            assert field in report, f"Missing field: {field}"

    def test_total_requests_count(self):
        """Total request count must be 30."""
        report = load_report()
        assert report["total_requests"] == 30
        state = load_state()
        assert len(state) == 30


# =============================================================================
# TIER 2: Token budget tests (need Bug 1 fixed - refill must replenish)
# =============================================================================

class TestTier2TokenValues:
    """Tests that verify correct token budget computation on refill."""

    def test_token_count_after_refill(self):
        """After svc_beta receives r01, its own budget must be replenished.

        svc_beta starts with budget [alpha:0, beta:9, delta:0, epsilon:0, gamma:0]
        (after its first INBOUND consumed 1 from initial 10).
        svc_beta receives r01 with token_state [alpha:7, beta:0, gamma:0, delta:0, epsilon:0].
        Correct merge: max([0,9,0,0,0], [7,0,0,0,0]) = [7,9,0,0,0], then +1 on beta = [7,10,0,0,0].

        If the refill replenishment is missing, svc_beta would be [7,9,0,0,0] instead.
        """
        state = load_state()
        # Find svc_beta's REFILL event for r01 (timestamp 300)
        refill_event = None
        for record in state:
            if (record["service"] == "svc_beta" and
                record["request_type"] == "REFILL" and
                record["timestamp"] == 300):
                refill_event = record
                break

        assert refill_event is not None, "Could not find svc_beta REFILL event at ts=300"
        budget = refill_event["token_budget"]
        assert budget["svc_beta"] == 10, (
            f"After refill+merge, svc_beta's own budget should be 10 (merge then replenish). "
            f"Got svc_beta={budget['svc_beta']}. If svc_beta=9, the post-merge replenishment is missing."
        )
        assert budget["svc_alpha"] == 7, f"svc_beta should have svc_alpha=7 after merge. Got {budget['svc_alpha']}"

    def test_token_budget_dominance(self):
        """After refill, the receiver's budget must strictly dominate the sender's state.

        svc_alpha receives r05 at ts=1050. Sender state is [alpha:7, beta:8, gamma:5, delta:4, epsilon:7].
        svc_alpha's budget before this refill is [alpha:1, beta:0, delta:0, epsilon:0, gamma:0].

        Correct: merge gives [7,8,5,4,7], then replenish alpha -> [8,8,5,4,7].
        This strictly dominates [7,8,5,4,7] because alpha:8 > 7.

        If replenishment is missing: merge gives [7,8,5,4,7] which EQUALS sender state.
        Equal does NOT satisfy strict dominance (all >= but not any >).
        """
        state = load_state()

        # Check svc_alpha's refill r05 (ts=1050)
        refill_event = None
        for record in state:
            if (record["service"] == "svc_alpha" and
                record["request_type"] == "REFILL" and
                record["timestamp"] == 1050):
                refill_event = record
                break

        assert refill_event is not None, "Could not find svc_alpha REFILL event at ts=1050"
        budget = refill_event["token_budget"]
        sender_state = {"svc_alpha": 7, "svc_beta": 8, "svc_gamma": 5, "svc_delta": 4, "svc_epsilon": 7}

        # Receiver must dominate: all >= AND at least one >
        for svc in sender_state:
            assert budget[svc] >= sender_state[svc], (
                f"Receiver budget must be >= sender for all components. "
                f"{svc}: receiver={budget[svc]} < sender={sender_state[svc]}"
            )

        assert any(budget[s] > sender_state[s] for s in sender_state), (
            f"Receiver budget must strictly dominate sender state (at least one component >). "
            f"Got receiver={budget}, sender={sender_state}. "
            f"If they're equal, the post-merge replenishment on the receiver's own component is missing."
        )

    def test_final_token_values(self):
        """Each service's final own-budget must reflect all events processed.

        svc_alpha: 7 events (3 INBOUND cost=1 each + 2 BURST cost=3 each + 1 INBOUND cost=1 + 1 REFILL)
          Initial=10, consume: -1-3-1-3-1-1 = -10, refill merge gives higher then +1 = final own=7
        svc_beta: 6 events, final own=9 (from last REFILL r06 merge+replenish)

        The final own-budget for svc_alpha should be 7 and svc_beta should be 9.
        """
        state = load_state()
        # Find each service's last event
        last_by_service = {}
        for record in state:
            last_by_service[record["service"]] = record

        assert last_by_service["svc_alpha"]["token_budget"]["svc_alpha"] == 7, (
            f"svc_alpha's final own-budget should be 7. "
            f"Got {last_by_service['svc_alpha']['token_budget']['svc_alpha']}"
        )
        assert last_by_service["svc_beta"]["token_budget"]["svc_beta"] == 9, (
            f"svc_beta's final own-budget should be 9. "
            f"Got {last_by_service['svc_beta']['token_budget']['svc_beta']}"
        )
        assert last_by_service["svc_gamma"]["token_budget"]["svc_gamma"] == 2, (
            f"svc_gamma's final own-budget should be 2. "
            f"Got {last_by_service['svc_gamma']['token_budget']['svc_gamma']}"
        )


# =============================================================================
# TIER 3: Independence and scheduling tests (need Bugs 2+3 fixed)
# =============================================================================

class TestTier3ThrottleOrdering:
    """Tests that verify correct independence detection and scheduling order."""

    def test_scheduling_not_timestamp_based(self):
        """The scheduling order must NOT be a simple timestamp sort.

        A correct scheduling order uses priority-based topological sort
        of the conflict DAG. Since independent requests can be ordered freely,
        the correct topological sort (using budget-sum tiebreaking) differs from
        pure timestamp ordering.

        The timestamp-sorted order would be [0,1,2,3,...,29] since requests
        are indexed by ascending timestamp. A correct priority-based sort
        reorders independent requests based on budget priority.
        """
        report = load_report()

        # Timestamp order is just [0, 1, 2, ..., 29]
        timestamp_order = list(range(30))
        scheduling_order = report["scheduling_order"]

        assert scheduling_order != timestamp_order, (
            "Scheduling order equals timestamp order. This suggests the implementation "
            "is sorting by physical timestamp instead of computing a priority-based "
            "topological sort of the conflict partial order. Physical time != scheduling "
            "priority in rate-limited systems."
        )

    def test_independent_pair_count(self):
        """Exactly 219 request pairs must be identified as independent.

        With 30 requests there are 435 total pairs.
        Correct analysis: 216 conflict + 219 independent = 435.

        If independence detection only catches equal budgets (instead of
        mutually non-dominating budgets), the count will be near 0.
        """
        report = load_report()
        assert report["independent_count"] == 219, (
            f"Expected exactly 219 independent pairs, got {report['independent_count']}. "
            f"Common errors: 0 (checking budget equality instead of mutual non-dominance), "
            f"or wrong total due to incorrect budget values from missing replenishment."
        )

    def test_conflict_coverage_and_asymmetry(self):
        """The conflict relation must be asymmetric AND the counts must sum correctly.

        Verifies:
        1. asymmetry_holds is True
        2. conflict_count + independent_count = 435 (total pairs)
        3. The independent count doesn't fall below the theoretical minimum
           for a 30-request trace with 5 services
        """
        report = load_report()

        assert report["asymmetry_holds"] is True, (
            "Asymmetry check failed. This indicates either incorrect token "
            "budget values or a bug in conflict detection."
        )

        total_pairs = 30 * 29 // 2  # 435
        conflicts = report["conflict_count"]
        independent = report["independent_count"]

        assert conflicts + independent == total_pairs, (
            f"Conflicts ({conflicts}) + independent ({independent}) = {conflicts + independent}, "
            f"expected {total_pairs}. Every pair must be classified as either conflict or independent."
        )

        # With 5 services and varied budget evolution, there MUST be independent pairs
        assert independent >= 100, (
            f"Only {independent} independent pairs detected. With 5 services and varied "
            f"budget evolution, many request pairs must have incomparable budgets. "
            f"A count near 0 indicates broken independence detection."
        )


# =============================================================================
# TIER 4: Full consistency tests (need ALL bugs fixed)
# =============================================================================

class TestTier4FullConsistency:
    """Tests that require all bugs to be fixed simultaneously."""

    def test_throttle_fingerprint(self):
        """The throttle graph fingerprint must match the expected value.

        This is a SHA-256 hash of the complete scheduling graph structure.
        It depends on:
        - Correct token budget values (Bug 1)
        - Correct independence detection (Bug 2)
        - Correct conflict classification (Bug 3)
        - Correct fingerprint computation (Bug 4)

        All four bugs must be fixed for this to match.
        """
        report = load_report()
        expected_fingerprint = "06f7a32287275aa6"
        assert report["throttle_fingerprint"] == expected_fingerprint, (
            f"Throttle fingerprint mismatch. Expected '{expected_fingerprint}', "
            f"got '{report['throttle_fingerprint']}'. This hash depends on the entire "
            f"scheduling graph being correct."
        )

    def test_full_consistency(self):
        """Cross-validate all metrics for internal consistency.

        Verifies:
        - Exact conflict count (216) and independent count (219)
        - conflict + independent = 435 (total pairs)
        - Scheduling order is NOT timestamp order
        - Scheduling order is a valid permutation
        - Budget values at final requests are correct

        This test requires all bugs to be fixed because it checks
        exact counts (need Bug 1 + Bug 2), ordering (need Bug 3),
        and final budget values (need Bug 1).
        """
        report = load_report()
        state = load_state()

        # Exact counts check (needs Bug 1 for correct budgets + Bug 2 for correct classification)
        assert report["conflict_count"] == 216, (
            f"Expected 216 conflict pairs, got {report['conflict_count']}"
        )
        assert report["independent_count"] == 219, (
            f"Expected 219 independent pairs, got {report['independent_count']}"
        )

        # Sum check
        n = report["total_requests"]
        total_pairs = n * (n - 1) // 2
        conflicts = report["conflict_count"]
        independent = report["independent_count"]
        assert conflicts + independent == total_pairs, (
            f"Conflicts ({conflicts}) + independent ({independent}) = {conflicts + independent}, "
            f"expected {total_pairs}"
        )

        # Scheduling order must not be timestamp order (needs Bug 3 fixed)
        timestamp_order = list(range(n))
        assert report["scheduling_order"] != timestamp_order, (
            "Scheduling order should differ from timestamp order"
        )

        # Scheduling order completeness
        assert sorted(report["scheduling_order"]) == list(range(n)), (
            "Scheduling order must be a permutation of all request indices"
        )

        # Final budget values (needs Bug 1 for correct replenishment cascade)
        last_alpha = None
        for record in reversed(state):
            if record["service"] == "svc_alpha":
                last_alpha = record
                break
        assert last_alpha is not None
        assert last_alpha["token_budget"]["svc_alpha"] == 7, (
            f"svc_alpha's final budget should be 7, got {last_alpha['token_budget']['svc_alpha']}"
        )

        last_beta = None
        for record in reversed(state):
            if record["service"] == "svc_beta":
                last_beta = record
                break
        assert last_beta is not None
        assert last_beta["token_budget"]["svc_beta"] == 9, (
            f"svc_beta's final budget should be 9, got {last_beta['token_budget']['svc_beta']}"
        )

        last_delta = None
        for record in reversed(state):
            if record["service"] == "svc_delta":
                last_delta = record
                break
        assert last_delta is not None
        assert last_delta["token_budget"]["svc_delta"] == 0, (
            f"svc_delta's final budget should be 0, got {last_delta['token_budget']['svc_delta']}"
        )
