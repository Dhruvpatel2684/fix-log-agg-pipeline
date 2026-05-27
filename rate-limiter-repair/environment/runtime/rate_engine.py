"""
Rate Engine - Main entrypoint for distributed request log processing.

Reads a request log, processes requests through the token bucket state machine,
performs throttle analysis, and writes output files.

Output files:
- /app/runtime/throttle_state.jsonl: Per-request token budget state
- /app/runtime/throttle_report.json: Throttle analysis summary with fingerprint
"""

import os
import sys

# Ensure runtime directory is in path
runtime_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, runtime_dir)

from request_parser import parse_request_log, get_service_ids
from token_engine import TokenEngine
from throttle_analyzer import ThrottleAnalyzer
from report_writer import write_throttle_state, write_throttle_report


def main():
    """Main processing flow."""
    # Locate input file
    request_log_path = os.path.join(runtime_dir, "request_log.txt")

    if not os.path.exists(request_log_path):
        print(f"ERROR: Request log not found at {request_log_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[rate_engine] Loading request log from {request_log_path}")

    # Step 1: Parse requests
    requests = parse_request_log(request_log_path)
    service_ids = get_service_ids(requests)
    print(f"[rate_engine] Parsed {len(requests)} requests across {len(service_ids)} services")

    # Step 2: Process through token bucket engine
    engine = TokenEngine(service_ids)
    request_budgets = engine.process_all(requests)
    print(f"[rate_engine] Token budgets computed for all requests")

    # Step 3: Throttle analysis
    analyzer = ThrottleAnalyzer(request_budgets)
    analyzer.analyze()
    print(f"[rate_engine] Throttle analysis complete: "
          f"{analyzer.get_conflict_count()} conflict pairs, "
          f"{analyzer.get_independent_count()} independent pairs")

    # Step 4: Write outputs
    state_path = os.path.join(runtime_dir, "throttle_state.jsonl")
    report_path = os.path.join(runtime_dir, "throttle_report.json")

    write_throttle_state(request_budgets, state_path)
    write_throttle_report(analyzer, request_budgets, service_ids, report_path)

    print(f"[rate_engine] Output written to:")
    print(f"  - {state_path}")
    print(f"  - {report_path}")
    print(f"[rate_engine] Done.")


if __name__ == "__main__":
    main()
