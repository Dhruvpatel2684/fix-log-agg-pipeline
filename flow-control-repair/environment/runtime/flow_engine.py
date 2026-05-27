"""
Flow Engine - Main entrypoint for connection ACK log processing.

Reads an ACK log, processes packets through the congestion window state machine,
performs congestion analysis, and writes output files.

Output files:
- /app/runtime/congestion_state.jsonl: Per-packet congestion window state
- /app/runtime/congestion_report.json: Congestion analysis summary with fingerprint
"""

import os
import sys

# Ensure runtime directory is in path
runtime_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, runtime_dir)

from ack_parser import parse_ack_log, get_connection_ids
from window_engine import WindowEngine
from congestion_analyzer import CongestionAnalyzer
from report_writer import write_congestion_state, write_congestion_report


def main():
    """Main processing flow."""
    # Locate input file
    ack_log_path = os.path.join(runtime_dir, "ack_log.txt")

    if not os.path.exists(ack_log_path):
        print(f"ERROR: ACK log not found at {ack_log_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[flow_engine] Loading ACK log from {ack_log_path}")

    # Step 1: Parse packets
    packets = parse_ack_log(ack_log_path)
    connection_ids = get_connection_ids(packets)
    print(f"[flow_engine] Parsed {len(packets)} packets across {len(connection_ids)} connections")

    # Step 2: Process through window engine
    engine = WindowEngine(connection_ids)
    packet_windows = engine.process_all(packets)
    print(f"[flow_engine] Congestion windows computed for all packets")

    # Step 3: Congestion analysis
    analyzer = CongestionAnalyzer(packet_windows)
    analyzer.analyze()
    print(f"[flow_engine] Congestion analysis complete: "
          f"{analyzer.get_competing_count()} competing pairs, "
          f"{analyzer.get_contention_free_count()} contention-free pairs")

    # Step 4: Write outputs
    state_path = os.path.join(runtime_dir, "congestion_state.jsonl")
    report_path = os.path.join(runtime_dir, "congestion_report.json")

    write_congestion_state(packet_windows, state_path)
    write_congestion_report(analyzer, packet_windows, connection_ids, report_path)

    print(f"[flow_engine] Output written to:")
    print(f"  - {state_path}")
    print(f"  - {report_path}")
    print(f"[flow_engine] Done.")


if __name__ == "__main__":
    main()
