"""
Report writer for congestion analysis output.

Produces two output files:
- congestion_state.jsonl: Per-packet state (one JSON object per line)
- congestion_report.json: Summary report with statistics and fingerprint
"""

import json
import hashlib
from typing import Dict, List, Tuple
from ack_parser import Packet
from congestion_analyzer import CongestionAnalyzer


def write_congestion_state(packet_windows: List[Tuple[Packet, Dict[str, int]]],
                           output_path: str):
    """Write per-packet state to a JSONL file.

    Each line contains:
    - packet_index: position in processing order
    - timestamp: arrival time
    - connection: connection ID
    - ack_type: DATA/DUPLEX/SACK
    - congestion_window: window state after this packet
    """
    with open(output_path, "w") as f:
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


def compute_congestion_fingerprint(analyzer: CongestionAnalyzer,
                                   packet_windows: List[Tuple[Packet, Dict[str, int]]]) -> str:
    """Compute a deterministic fingerprint of the congestion graph.

    The fingerprint encodes the complete scheduling structure:
    - All competing edges (source -> target)
    - All contention-free pairs (sorted lexicographically)
    - Packet identifiers use timestamp_connection_type format

    This allows quick detection of scheduling graph drift between deployments.
    """
    n = len(packet_windows)
    edges = []

    for i in range(n):
        for j in range(i + 1, n):
            pi = packet_windows[i]
            pj = packet_windows[j]
            id_i = f"{pi[0].timestamp}_{pi[0].connection}_{pi[0].ack_type}"
            id_j = f"{pj[0].timestamp}_{pj[0].connection}_{pj[0].ack_type}"

            window_i = pi[1]
            window_j = pj[1]

            # Determine relationship using the same logic as analyzer
            from congestion_analyzer import window_strictly_less, are_contention_free
            if are_contention_free(window_i, window_j):
                pair = tuple(sorted([id_i, id_j]))
                edges.append((pair[0], pair[1], "contention_free"))
            elif window_strictly_less(window_i, window_j):
                edges.append((id_i, id_j, "competing"))
            elif window_strictly_less(window_j, window_i):
                edges.append((id_j, id_i, "competing"))
            else:
                # Remaining incomparable windows — resolved by index order
                # consistent with the analyzer's total order extension
                edges.append((id_i, id_j, "competing"))

    edges.sort()
    fingerprint_data = json.dumps(edges, sort_keys=True)
    return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]


def write_congestion_report(analyzer: CongestionAnalyzer,
                            packet_windows: List[Tuple[Packet, Dict[str, int]]],
                            connection_ids: List[str],
                            output_path: str):
    """Write the congestion analysis summary report.

    Contains:
    - connection_ids: list of connections in the system
    - total_packets: number of packets processed
    - packets_per_connection: count per connection
    - competing_count: number of competing pairs
    - contention_free_count: number of contention-free pairs
    - scheduling_order: packet indices in scheduling order
    - asymmetry_holds: whether competing relation is asymmetric
    - congestion_fingerprint: hash of the complete scheduling graph
    """
    # Count packets per connection
    packets_per_connection = {}
    for packet, _ in packet_windows:
        conn = packet.connection
        packets_per_connection[conn] = packets_per_connection.get(conn, 0) + 1

    # Compute fingerprint
    fingerprint = compute_congestion_fingerprint(analyzer, packet_windows)

    report = {
        "connection_ids": sorted(connection_ids),
        "total_packets": len(packet_windows),
        "packets_per_connection": packets_per_connection,
        "competing_count": analyzer.get_competing_count(),
        "contention_free_count": analyzer.get_contention_free_count(),
        "scheduling_order": analyzer.get_scheduling_order(),
        "asymmetry_holds": analyzer.verify_asymmetry(),
        "congestion_fingerprint": fingerprint,
    }

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
