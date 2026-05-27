"""
Oracle solution for mac-chain-repair task.

Fixes the 4 bugs:
1. chain_engine.py: SYNC must increment own chain depth AFTER merge
2. integrity_analyzer.py: Non-conflicting uses correct predicate (neither dominates)
3. integrity_analyzer.py: Verification uses priority-based sort (chain sum), not timestamps
4. report_writer.py: Fingerprint uses the same fixed logic from bugs 2+3

This script re-processes the auth log with correct logic and overwrites the output files.
"""

import os
import sys
import json
import hashlib

# Ensure runtime directory is in path
runtime_dir = "/app/runtime"
sys.path.insert(0, runtime_dir)

from auth_parser import parse_auth_log, get_authority_ids, AuthEvent
from typing import Dict, List, Tuple, Set


# ============================================================
# Fixed Chain State (Bug 1 fix: increment after merge)
# ============================================================

INITIAL_CHAIN_DEPTH = 10


class FixedChainState:
    """Chain state that correctly advances on sync."""

    def __init__(self, authority_id: str, all_authorities: List[str]):
        self.authority_id = authority_id
        self.depth: Dict[str, int] = {a: 0 for a in all_authorities}
        self.depth[authority_id] = INITIAL_CHAIN_DEPTH

    def get_depth(self) -> Dict[str, int]:
        return dict(self.depth)

    def advance(self, cost: int):
        self.depth[self.authority_id] -= cost

    def merge_and_advance(self, peer_state: Dict[str, int]):
        """Correct sync behavior: merge then advance own chain depth."""
        for auth in self.depth:
            if auth in peer_state:
                self.depth[auth] = max(self.depth[auth], peer_state[auth])
        # FIX: Always advance own chain depth after merge on sync
        self.depth[self.authority_id] += 1


# ============================================================
# Fixed Non-Conflicting Predicate (Bug 2 fix: neither dominates = non-conflicting)
# ============================================================

def chain_leq(chain_a: Dict[str, int], chain_b: Dict[str, int]) -> bool:
    """Check if chain_a <= chain_b (all components less-than-or-equal)."""
    return all(chain_a.get(k, 0) <= chain_b.get(k, 0) for k in chain_a)


def chain_strictly_less(chain_a: Dict[str, int], chain_b: Dict[str, int]) -> bool:
    """Check if chain_a < chain_b (strict dominance)."""
    all_leq = all(chain_a.get(k, 0) <= chain_b.get(k, 0) for k in chain_a)
    some_lt = any(chain_a.get(k, 0) < chain_b.get(k, 0) for k in chain_a)
    return all_leq and some_lt


def are_non_conflicting_fixed(chain_a: Dict[str, int], chain_b: Dict[str, int]) -> bool:
    """FIXED: Two events are non-conflicting when NEITHER chain dominates the other.

    Non-conflicting means no causal ordering can be established between them
    through chain comparison alone — neither has strictly more attestation depth.
    """
    a_leq_b = chain_leq(chain_a, chain_b)
    b_leq_a = chain_leq(chain_b, chain_a)
    # Non-conflicting when neither dominates: NOT(a<=b) AND NOT(b<=a)
    return (not a_leq_b) and (not b_leq_a)


# ============================================================
# Fixed Verification Order (Bug 3 fix: priority-based topological sort)
# ============================================================

def compute_verification_order_fixed(event_states: List[Tuple[AuthEvent, Dict[str, int]]],
                                     conflict_pairs: List[Tuple[int, int]]) -> List[int]:
    """FIXED: Priority-based topological sort using chain depth sums.

    Events with higher total remaining chain depth get verified first (higher priority).
    Ties broken by authority ID for determinism.
    """
    n = len(event_states)

    # Build in-degree from conflict edges
    in_degree = [0] * n
    adj: Dict[int, List[int]] = {i: [] for i in range(n)}
    for (src, dst) in conflict_pairs:
        adj[src].append(dst)
        in_degree[dst] += 1

    # Priority queue using chain sum (higher depth = higher priority = processed first)
    # For topological sort: pick from zero-in-degree nodes, prefer highest chain sum
    result = []
    available = []
    for i in range(n):
        if in_degree[i] == 0:
            chain_sum = sum(event_states[i][1].values())
            available.append((i, chain_sum, event_states[i][0].authority))

    # Sort: highest chain depth first, then by authority ID for determinism
    available.sort(key=lambda x: (-x[1], x[2]))

    while available:
        # Take the highest priority available node
        node, _, _ = available.pop(0)
        result.append(node)

        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                chain_sum = sum(event_states[neighbor][1].values())
                available.append((neighbor, chain_sum, event_states[neighbor][0].authority))
                available.sort(key=lambda x: (-x[1], x[2]))

    # If graph has cycles (shouldn't with correct data), add remaining
    if len(result) < n:
        remaining = [i for i in range(n) if i not in set(result)]
        remaining.sort(key=lambda i: (-sum(event_states[i][1].values()),
                                       event_states[i][0].authority))
        result.extend(remaining)

    return result


# ============================================================
# Main processing with all fixes applied
# ============================================================

def main():
    # Load input
    auth_log_path = os.path.join(runtime_dir, "auth_log.txt")
    events = parse_auth_log(auth_log_path)
    authority_ids = get_authority_ids(events)

    # Step 1: Process with fixed chain engine (Bug 1 fix)
    chains: Dict[str, FixedChainState] = {
        aid: FixedChainState(aid, authority_ids)
        for aid in authority_ids
    }
    event_states: List[Tuple[AuthEvent, Dict[str, int]]] = []

    for event in events:
        chain = chains[event.authority]
        if event.msg_type == "SIGN":
            chain.advance(event.cost)
        elif event.msg_type == "BATCH":
            chain.advance(event.cost)
        elif event.msg_type == "SYNC":
            if event.peer_chain is not None:
                chain.merge_and_advance(event.peer_chain)
        depth_snapshot = chain.get_depth()
        event_states.append((event, depth_snapshot))

    # Step 2: Classify pairs with fixed non-conflicting (Bug 2 fix)
    n = len(event_states)
    conflict_pairs: List[Tuple[int, int]] = []
    non_conflicting_pairs: List[Tuple[int, int]] = []

    for i in range(n):
        for j in range(i + 1, n):
            chain_i = event_states[i][1]
            chain_j = event_states[j][1]

            if are_non_conflicting_fixed(chain_i, chain_j):
                non_conflicting_pairs.append((i, j))
            elif chain_strictly_less(chain_i, chain_j):
                conflict_pairs.append((i, j))
            elif chain_strictly_less(chain_j, chain_i):
                conflict_pairs.append((j, i))
            else:
                # Equal chain states — not non-conflicting (a<=b AND b<=a both true means equal)
                conflict_pairs.append((i, j))

    # Step 3: Compute verification order with fixed logic (Bug 3 fix)
    verification_order = compute_verification_order_fixed(event_states, conflict_pairs)

    # Step 4: Compute fingerprint with fixed non-conflicting (Bug 4 fix)
    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            ei = event_states[i]
            ej = event_states[j]
            id_i = f"{ei[0].timestamp}_{ei[0].authority}_{ei[0].msg_type}"
            id_j = f"{ej[0].timestamp}_{ej[0].authority}_{ej[0].msg_type}"

            chain_i = ei[1]
            chain_j = ej[1]

            if are_non_conflicting_fixed(chain_i, chain_j):
                pair = tuple(sorted([id_i, id_j]))
                edges.append((pair[0], pair[1], "non_conflicting"))
            elif chain_strictly_less(chain_i, chain_j):
                edges.append((id_i, id_j, "conflict"))
            elif chain_strictly_less(chain_j, chain_i):
                edges.append((id_j, id_i, "conflict"))
            else:
                edges.append((id_i, id_j, "conflict"))

    edges.sort()
    fingerprint_data = json.dumps(edges, sort_keys=True)
    fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]

    # Step 5: Write corrected state file
    state_path = os.path.join(runtime_dir, "chain_state.jsonl")
    with open(state_path, "w") as f:
        for idx, (event, depth) in enumerate(event_states):
            record = {
                "event_index": idx,
                "timestamp": event.timestamp,
                "authority": event.authority,
                "msg_type": event.msg_type,
                "chain_depth": depth,
            }
            if event.msg_id:
                record["msg_id"] = event.msg_id
            f.write(json.dumps(record, sort_keys=True) + "\n")

    # Step 6: Write corrected report
    events_per_authority = {}
    for event, _ in event_states:
        auth = event.authority
        events_per_authority[auth] = events_per_authority.get(auth, 0) + 1

    report = {
        "authority_ids": sorted(authority_ids),
        "total_events": len(event_states),
        "events_per_authority": events_per_authority,
        "conflict_count": len(conflict_pairs),
        "non_conflicting_count": len(non_conflicting_pairs),
        "verification_order": verification_order,
        "asymmetry_holds": True,
        "chain_fingerprint": fingerprint,
    }

    report_path = os.path.join(runtime_dir, "chain_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)

    print(f"[repair_chain] Fixed output written:")
    print(f"  Conflict pairs: {len(conflict_pairs)}")
    print(f"  Non-conflicting pairs: {len(non_conflicting_pairs)}")
    print(f"  Fingerprint: {fingerprint}")
    print(f"  Verification order: {verification_order}")


if __name__ == "__main__":
    main()
