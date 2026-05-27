"""
Oracle solution for flow-control-repair task.

Fixes the 4 bugs:
1. window_engine.py: SACK must advance own window AFTER merge
2. congestion_analyzer.py: Contention-free uses correct predicate (neither dominates)
3. congestion_analyzer.py: Scheduling uses priority-based sort (window sum), not timestamps
4. report_writer.py: Fingerprint uses the same fixed logic from bugs 2+3

This script re-processes the ACK log with correct logic and overwrites the output files.
"""

import os
import sys
import json
import hashlib

# Ensure runtime directory is in path
runtime_dir = "/app/runtime"
sys.path.insert(0, runtime_dir)

from ack_parser import parse_ack_log, get_connection_ids, Packet
from typing import Dict, List, Tuple, Set


# ============================================================
# Fixed Congestion Window (Bug 1 fix: advance after merge)
# ============================================================

INITIAL_WINDOW = 10


class FixedCongestionWindow:
    """Congestion window that correctly advances on SACK receipt."""

    def __init__(self, connection_id: str, all_connections: List[str]):
        self.connection_id = connection_id
        self.window: Dict[str, int] = {c: 0 for c in all_connections}
        self.window[connection_id] = INITIAL_WINDOW

    def get_window(self) -> Dict[str, int]:
        return dict(self.window)

    def consume(self, cost: int):
        self.window[self.connection_id] -= cost

    def merge_and_advance(self, peer_state: Dict[str, int]):
        """Correct SACK behavior: merge then advance own window."""
        for conn in self.window:
            if conn in peer_state:
                self.window[conn] = max(self.window[conn], peer_state[conn])
        # FIX: Always advance own window after merge on SACK
        self.window[self.connection_id] += 1


# ============================================================
# Fixed Contention-Free Predicate (Bug 2 fix: neither dominates = contention-free)
# ============================================================

def window_leq(window_a: Dict[str, int], window_b: Dict[str, int]) -> bool:
    """Check if window_a <= window_b (all components less-than-or-equal)."""
    return all(window_a.get(k, 0) <= window_b.get(k, 0) for k in window_a)


def window_strictly_less(window_a: Dict[str, int], window_b: Dict[str, int]) -> bool:
    """Check if window_a < window_b (strict dominance)."""
    all_leq = all(window_a.get(k, 0) <= window_b.get(k, 0) for k in window_a)
    some_lt = any(window_a.get(k, 0) < window_b.get(k, 0) for k in window_a)
    return all_leq and some_lt


def are_contention_free_fixed(window_a: Dict[str, int], window_b: Dict[str, int]) -> bool:
    """FIXED: Two packets are contention-free when NEITHER window dominates the other.

    Contention-free means no causal ordering can be established between them
    through window comparison alone — neither has strictly more capacity.
    """
    a_leq_b = window_leq(window_a, window_b)
    b_leq_a = window_leq(window_b, window_a)
    # Contention-free when neither dominates: NOT(a<=b) AND NOT(b<=a)
    return (not a_leq_b) and (not b_leq_a)


# ============================================================
# Fixed Scheduling Order (Bug 3 fix: priority-based topological sort)
# ============================================================

def compute_scheduling_order_fixed(packet_windows: List[Tuple[Packet, Dict[str, int]]],
                                   competing_pairs: List[Tuple[int, int]]) -> List[int]:
    """FIXED: Priority-based topological sort using window sums.

    Packets with higher total remaining window get scheduled first (higher priority).
    Ties broken by connection ID for determinism.
    """
    n = len(packet_windows)

    # Build in-degree from competing edges
    in_degree = [0] * n
    adj: Dict[int, List[int]] = {i: [] for i in range(n)}
    for (src, dst) in competing_pairs:
        adj[src].append(dst)
        in_degree[dst] += 1

    # Priority queue using window sum (higher window = higher priority = processed first)
    # For topological sort: pick from zero-in-degree nodes, prefer highest window sum
    result = []
    available = []
    for i in range(n):
        if in_degree[i] == 0:
            window_sum = sum(packet_windows[i][1].values())
            available.append((i, window_sum, packet_windows[i][0].connection))

    # Sort: highest window first, then by connection ID for determinism
    available.sort(key=lambda x: (-x[1], x[2]))

    while available:
        # Take the highest priority available node
        node, _, _ = available.pop(0)
        result.append(node)

        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                window_sum = sum(packet_windows[neighbor][1].values())
                available.append((neighbor, window_sum, packet_windows[neighbor][0].connection))
                available.sort(key=lambda x: (-x[1], x[2]))

    # If graph has cycles (shouldn't with correct data), add remaining
    if len(result) < n:
        remaining = [i for i in range(n) if i not in set(result)]
        remaining.sort(key=lambda i: (-sum(packet_windows[i][1].values()),
                                       packet_windows[i][0].connection))
        result.extend(remaining)

    return result


# ============================================================
# Main processing with all fixes applied
# ============================================================

def main():
    # Load input
    ack_log_path = os.path.join(runtime_dir, "ack_log.txt")
    packets = parse_ack_log(ack_log_path)
    connection_ids = get_connection_ids(packets)

    # Step 1: Process with fixed window engine (Bug 1 fix)
    windows: Dict[str, FixedCongestionWindow] = {
        cid: FixedCongestionWindow(cid, connection_ids)
        for cid in connection_ids
    }
    packet_windows: List[Tuple[Packet, Dict[str, int]]] = []

    for packet in packets:
        window = windows[packet.connection]
        if packet.ack_type == "DATA":
            window.consume(packet.cost)
        elif packet.ack_type == "DUPLEX":
            window.consume(packet.cost)
        elif packet.ack_type == "SACK":
            if packet.peer_window is not None:
                window.merge_and_advance(packet.peer_window)
        window_snapshot = window.get_window()
        packet_windows.append((packet, window_snapshot))

    # Step 2: Classify pairs with fixed contention-free (Bug 2 fix)
    n = len(packet_windows)
    competing_pairs: List[Tuple[int, int]] = []
    contention_free_pairs: List[Tuple[int, int]] = []

    for i in range(n):
        for j in range(i + 1, n):
            window_i = packet_windows[i][1]
            window_j = packet_windows[j][1]

            if are_contention_free_fixed(window_i, window_j):
                contention_free_pairs.append((i, j))
            elif window_strictly_less(window_i, window_j):
                competing_pairs.append((i, j))
            elif window_strictly_less(window_j, window_i):
                competing_pairs.append((j, i))
            else:
                # Equal windows — not contention-free (a<=b AND b<=a both true means equal)
                competing_pairs.append((i, j))

    # Step 3: Compute scheduling order with fixed logic (Bug 3 fix)
    scheduling_order = compute_scheduling_order_fixed(packet_windows, competing_pairs)

    # Step 4: Compute fingerprint with fixed contention-free (Bug 4 fix)
    edges = []
    for i in range(n):
        for j in range(i + 1, n):
            pi = packet_windows[i]
            pj = packet_windows[j]
            id_i = f"{pi[0].timestamp}_{pi[0].connection}_{pi[0].ack_type}"
            id_j = f"{pj[0].timestamp}_{pj[0].connection}_{pj[0].ack_type}"

            window_i = pi[1]
            window_j = pj[1]

            if are_contention_free_fixed(window_i, window_j):
                pair = tuple(sorted([id_i, id_j]))
                edges.append((pair[0], pair[1], "contention_free"))
            elif window_strictly_less(window_i, window_j):
                edges.append((id_i, id_j, "competing"))
            elif window_strictly_less(window_j, window_i):
                edges.append((id_j, id_i, "competing"))
            else:
                edges.append((id_i, id_j, "competing"))

    edges.sort()
    fingerprint_data = json.dumps(edges, sort_keys=True)
    fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]

    # Step 5: Write corrected state file
    state_path = os.path.join(runtime_dir, "congestion_state.jsonl")
    with open(state_path, "w") as f:
        for idx, (packet, window) in enumerate(packet_windows):
            record = {
                "packet_index": idx,
                "timestamp": packet.timestamp,
                "connection": packet.connection,
                "ack_type": packet.ack_type,
                "congestion_window": window,
            }
            if packet.msg_id:
                record["msg_id"] = packet.msg_id
            f.write(json.dumps(record, sort_keys=True) + "\n")

    # Step 6: Write corrected report
    packets_per_connection = {}
    for packet, _ in packet_windows:
        conn = packet.connection
        packets_per_connection[conn] = packets_per_connection.get(conn, 0) + 1

    report = {
        "connection_ids": sorted(connection_ids),
        "total_packets": len(packet_windows),
        "packets_per_connection": packets_per_connection,
        "competing_count": len(competing_pairs),
        "contention_free_count": len(contention_free_pairs),
        "scheduling_order": scheduling_order,
        "asymmetry_holds": True,
        "congestion_fingerprint": fingerprint,
    }

    report_path = os.path.join(runtime_dir, "congestion_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)

    print(f"[repair_flow] Fixed output written:")
    print(f"  Competing pairs: {len(competing_pairs)}")
    print(f"  Contention-free pairs: {len(contention_free_pairs)}")
    print(f"  Fingerprint: {fingerprint}")
    print(f"  Scheduling order: {scheduling_order}")


if __name__ == "__main__":
    main()
