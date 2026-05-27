"""
Oracle solution for rate-limiter-repair task.

Fixes the 4 bugs:
1. token_engine.py: REFILL must increment own budget AFTER merge
2. throttle_analyzer.py: Independence uses correct predicate (neither dominates)
3. throttle_analyzer.py: Scheduling uses priority-based sort (budget sum), not timestamps
4. report_writer.py: Fingerprint uses the same fixed logic from bugs 2+3

This script re-processes the request log with correct logic and overwrites the output files.
"""

import os
import sys
import json
import hashlib

# Ensure runtime directory is in path
runtime_dir = "/app/runtime"
sys.path.insert(0, runtime_dir)

from request_parser import parse_request_log, get_service_ids, Request
from typing import Dict, List, Tuple, Set


# ============================================================
# Fixed Token Bucket (Bug 1 fix: increment after merge)
# ============================================================

INITIAL_BUDGET = 10


class FixedTokenBucket:
    """Token bucket that correctly replenishes on refill."""

    def __init__(self, service_id: str, all_services: List[str]):
        self.service_id = service_id
        self.budget: Dict[str, int] = {s: 0 for s in all_services}
        self.budget[service_id] = INITIAL_BUDGET

    def get_budget(self) -> Dict[str, int]:
        return dict(self.budget)

    def consume(self, cost: int):
        self.budget[self.service_id] -= cost

    def merge_and_replenish(self, upstream_state: Dict[str, int]):
        """Correct refill behavior: merge then replenish own budget."""
        for svc in self.budget:
            if svc in upstream_state:
                self.budget[svc] = max(self.budget[svc], upstream_state[svc])
        # FIX: Always replenish own budget after merge on refill
        self.budget[self.service_id] += 1


# ============================================================
# Fixed Independence Predicate (Bug 2 fix: neither dominates = independent)
# ============================================================

def budget_leq(budget_a: Dict[str, int], budget_b: Dict[str, int]) -> bool:
    """Check if budget_a <= budget_b (all components less-than-or-equal)."""
    return all(budget_a.get(k, 0) <= budget_b.get(k, 0) for k in budget_a)


def budget_strictly_less(budget_a: Dict[str, int], budget_b: Dict[str, int]) -> bool:
    """Check if budget_a < budget_b (strict dominance)."""
    all_leq = all(budget_a.get(k, 0) <= budget_b.get(k, 0) for k in budget_a)
    some_lt = any(budget_a.get(k, 0) < budget_b.get(k, 0) for k in budget_a)
    return all_leq and some_lt


def are_independent_fixed(budget_a: Dict[str, int], budget_b: Dict[str, int]) -> bool:
    """FIXED: Two requests are independent when NEITHER budget dominates the other.

    Independence means no causal ordering can be established between them
    through budget comparison alone — neither has strictly more resources.
    """
    a_leq_b = budget_leq(budget_a, budget_b)
    b_leq_a = budget_leq(budget_b, budget_a)
    # Independent when neither dominates: NOT(a<=b) AND NOT(b<=a)
    return (not a_leq_b) and (not b_leq_a)


# ============================================================
# Fixed Scheduling Order (Bug 3 fix: priority-based topological sort)
# ============================================================

def compute_scheduling_order_fixed(request_budgets: List[Tuple[Request, Dict[str, int]]],
                                   conflict_pairs: List[Tuple[int, int]]) -> List[int]:
    """FIXED: Priority-based topological sort using budget sums.

    Requests with higher total remaining budget get scheduled first (higher priority).
    Ties broken by service ID for determinism.
    """
    n = len(request_budgets)

    # Build in-degree from conflict edges
    in_degree = [0] * n
    adj: Dict[int, List[int]] = {i: [] for i in range(n)}
    for (src, dst) in conflict_pairs:
        adj[src].append(dst)
        in_degree[dst] += 1

    # Priority queue using budget sum (higher budget = higher priority = processed first)
    # For topological sort: pick from zero-in-degree nodes, prefer highest budget sum
    result = []
    available = []
    for i in range(n):
        if in_degree[i] == 0:
            budget_sum = sum(request_budgets[i][1].values())
            available.append((i, budget_sum, request_budgets[i][0].service))

    # Sort: highest budget first, then by service ID for determinism
    available.sort(key=lambda x: (-x[1], x[2]))

    while available:
        # Take the highest priority available node
        node, _, _ = available.pop(0)
        result.append(node)

        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                budget_sum = sum(request_budgets[neighbor][1].values())
                available.append((neighbor, budget_sum, request_budgets[neighbor][0].service))
                available.sort(key=lambda x: (-x[1], x[2]))

    # If graph has cycles (shouldn't with correct data), add remaining
    if len(result) < n:
        remaining = [i for i in range(n) if i not in set(result)]
        remaining.sort(key=lambda i: (-sum(request_budgets[i][1].values()),
                                       request_budgets[i][0].service))
        result.extend(remaining)

    return result


# ============================================================
# Main processing with all fixes applied
# ============================================================

def main():
    # Load input
    request_log_path = os.path.join(runtime_dir, "request_log.txt")
    requests = parse_request_log(request_log_path)
    service_ids = get_service_ids(requests)

    # Step 1: Process with fixed token engine (Bug 1 fix)
    buckets: Dict[str, FixedTokenBucket] = {
        sid: FixedTokenBucket(sid, service_ids)
        for sid in service_ids
    }
    request_budgets: List[Tuple[Request, Dict[str, int]]] = []

    for request in requests:
        bucket = buckets[request.service]
        if request.request_type == "INBOUND":
            bucket.consume(request.cost)
        elif request.request_type == "BURST":
            bucket.consume(request.cost)
        elif request.request_type == "REFILL":
            if request.token_state is not None:
                bucket.merge_and_replenish(request.token_state)
        budget_snapshot = bucket.get_budget()
        request_budgets.append((request, budget_snapshot))

    # Step 2: Classify pairs with fixed independence (Bug 2 fix)
    n = len(request_budgets)
    conflict_pairs: List[Tuple[int, int]] = []
    independent_pairs: List[Tuple[int, int]] = []

    for i in range(n):
        for j in range(i + 1, n):
            budget_i = request_budgets[i][1]
            budget_j = request_budgets[j][1]

            if are_independent_fixed(budget_i, budget_j):
                independent_pairs.append((i, j))
            elif budget_strictly_less(budget_i, budget_j):
                conflict_pairs.append((i, j))
            elif budget_strictly_less(budget_j, budget_i):
                conflict_pairs.append((j, i))
            else:
                # Equal budgets — not independent (a<=b AND b<=a both true means equal)
                conflict_pairs.append((i, j))

    # Step 3: Compute scheduling order with fixed logic (Bug 3 fix)
    scheduling_order = compute_scheduling_order_fixed(request_budgets, conflict_pairs)

    # Step 4: Compute fingerprint with fixed independence (Bug 4 fix)
    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            ri = request_budgets[i]
            rj = request_budgets[j]
            id_i = f"{ri[0].timestamp}_{ri[0].service}_{ri[0].request_type}"
            id_j = f"{rj[0].timestamp}_{rj[0].service}_{rj[0].request_type}"

            budget_i = ri[1]
            budget_j = rj[1]

            if are_independent_fixed(budget_i, budget_j):
                pair = tuple(sorted([id_i, id_j]))
                edges.append((pair[0], pair[1], "independent"))
            elif budget_strictly_less(budget_i, budget_j):
                edges.append((id_i, id_j, "conflict"))
            elif budget_strictly_less(budget_j, budget_i):
                edges.append((id_j, id_i, "conflict"))
            else:
                edges.append((id_i, id_j, "conflict"))

    edges.sort()
    fingerprint_data = json.dumps(edges, sort_keys=True)
    fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]

    # Step 5: Write corrected state file
    state_path = os.path.join(runtime_dir, "throttle_state.jsonl")
    with open(state_path, "w") as f:
        for idx, (request, budget) in enumerate(request_budgets):
            record = {
                "request_index": idx,
                "timestamp": request.timestamp,
                "service": request.service,
                "request_type": request.request_type,
                "token_budget": budget,
            }
            if request.msg_id:
                record["msg_id"] = request.msg_id
            f.write(json.dumps(record, sort_keys=True) + "\n")

    # Step 6: Write corrected report
    requests_per_service = {}
    for request, _ in request_budgets:
        svc = request.service
        requests_per_service[svc] = requests_per_service.get(svc, 0) + 1

    report = {
        "service_ids": sorted(service_ids),
        "total_requests": len(request_budgets),
        "requests_per_service": requests_per_service,
        "conflict_count": len(conflict_pairs),
        "independent_count": len(independent_pairs),
        "scheduling_order": scheduling_order,
        "asymmetry_holds": True,
        "throttle_fingerprint": fingerprint,
    }

    report_path = os.path.join(runtime_dir, "throttle_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)

    print(f"[repair_throttle] Fixed output written:")
    print(f"  Conflict pairs: {len(conflict_pairs)}")
    print(f"  Independent pairs: {len(independent_pairs)}")
    print(f"  Fingerprint: {fingerprint}")
    print(f"  Scheduling order: {scheduling_order}")


if __name__ == "__main__":
    main()
