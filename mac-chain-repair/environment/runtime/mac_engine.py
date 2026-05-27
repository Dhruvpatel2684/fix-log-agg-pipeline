"""
MAC Engine - Main entrypoint for distributed auth log processing.

Reads an authentication log, processes events through the chain state machine,
performs integrity analysis, and writes output files.

Output files:
- /app/runtime/chain_state.jsonl: Per-event chain depth state
- /app/runtime/chain_report.json: Integrity analysis summary with fingerprint
"""

import os
import sys

# Ensure runtime directory is in path
runtime_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, runtime_dir)

from auth_parser import parse_auth_log, get_authority_ids
from chain_engine import ChainEngine
from integrity_analyzer import IntegrityAnalyzer
from report_writer import write_chain_state, write_chain_report


def main():
    """Main processing flow."""
    # Locate input file
    auth_log_path = os.path.join(runtime_dir, "auth_log.txt")

    if not os.path.exists(auth_log_path):
        print(f"ERROR: Auth log not found at {auth_log_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[mac_engine] Loading auth log from {auth_log_path}")

    # Step 1: Parse events
    events = parse_auth_log(auth_log_path)
    authority_ids = get_authority_ids(events)
    print(f"[mac_engine] Parsed {len(events)} events across {len(authority_ids)} authorities")

    # Step 2: Process through chain engine
    engine = ChainEngine(authority_ids)
    event_states = engine.process_all(events)
    print(f"[mac_engine] Chain states computed for all events")

    # Step 3: Integrity analysis
    analyzer = IntegrityAnalyzer(event_states)
    analyzer.analyze()
    print(f"[mac_engine] Integrity analysis complete: "
          f"{analyzer.get_conflict_count()} conflict pairs, "
          f"{analyzer.get_non_conflicting_count()} non-conflicting pairs")

    # Step 4: Write outputs
    state_path = os.path.join(runtime_dir, "chain_state.jsonl")
    report_path = os.path.join(runtime_dir, "chain_report.json")

    write_chain_state(event_states, state_path)
    write_chain_report(analyzer, event_states, authority_ids, report_path)

    print(f"[mac_engine] Output written to:")
    print(f"  - {state_path}")
    print(f"  - {report_path}")
    print(f"[mac_engine] Done.")


if __name__ == "__main__":
    main()
