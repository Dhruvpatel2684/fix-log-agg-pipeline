"""
Report writer for integrity analysis output.

Produces two output files:
- chain_state.jsonl: Per-event state (one JSON object per line)
- chain_report.json: Summary report with statistics and fingerprint
"""

import json
import hashlib
from typing import Dict, List, Tuple
from auth_parser import AuthEvent
from integrity_analyzer import IntegrityAnalyzer


def write_chain_state(event_states: List[Tuple[AuthEvent, Dict[str, int]]],
                      output_path: str):
    """Write per-event state to a JSONL file.

    Each line contains:
    - event_index: position in processing order
    - timestamp: attestation time
    - authority: authority ID
    - msg_type: SIGN/BATCH/SYNC
    - chain_depth: chain state after this event
    """
    with open(output_path, "w") as f:
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


def compute_chain_fingerprint(analyzer: IntegrityAnalyzer,
                              event_states: List[Tuple[AuthEvent, Dict[str, int]]]) -> str:
    """Compute a deterministic fingerprint of the verification graph.

    The fingerprint encodes the complete verification structure:
    - All conflict edges (source -> target)
    - All non-conflicting pairs (sorted lexicographically)
    - Event identifiers use timestamp_authority_type format

    This allows quick detection of verification graph drift between deployments.
    """
    n = len(event_states)
    edges = []

    for i in range(n):
        for j in range(i + 1, n):
            ei = event_states[i]
            ej = event_states[j]
            id_i = f"{ei[0].timestamp}_{ei[0].authority}_{ei[0].msg_type}"
            id_j = f"{ej[0].timestamp}_{ej[0].authority}_{ej[0].msg_type}"

            chain_i = ei[1]
            chain_j = ej[1]

            # Determine relationship using the same logic as analyzer
            from integrity_analyzer import chain_strictly_less, are_non_conflicting
            if are_non_conflicting(chain_i, chain_j):
                pair = tuple(sorted([id_i, id_j]))
                edges.append((pair[0], pair[1], "non_conflicting"))
            elif chain_strictly_less(chain_i, chain_j):
                edges.append((id_i, id_j, "conflict"))
            elif chain_strictly_less(chain_j, chain_i):
                edges.append((id_j, id_i, "conflict"))
            else:
                # Remaining incomparable states — resolved by index order
                # consistent with the analyzer's total order extension
                edges.append((id_i, id_j, "conflict"))

    edges.sort()
    fingerprint_data = json.dumps(edges, sort_keys=True)
    return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]


def write_chain_report(analyzer: IntegrityAnalyzer,
                       event_states: List[Tuple[AuthEvent, Dict[str, int]]],
                       authority_ids: List[str],
                       output_path: str):
    """Write the integrity analysis summary report.

    Contains:
    - authority_ids: list of authorities in the system
    - total_events: number of events processed
    - events_per_authority: count per authority
    - conflict_count: number of conflict pairs
    - non_conflicting_count: number of non-conflicting pairs
    - verification_order: event indices in verification order
    - asymmetry_holds: whether conflict relation is asymmetric
    - chain_fingerprint: hash of the complete verification graph
    """
    # Count events per authority
    events_per_authority = {}
    for event, _ in event_states:
        auth = event.authority
        events_per_authority[auth] = events_per_authority.get(auth, 0) + 1

    # Compute fingerprint
    fingerprint = compute_chain_fingerprint(analyzer, event_states)

    report = {
        "authority_ids": sorted(authority_ids),
        "total_events": len(event_states),
        "events_per_authority": events_per_authority,
        "conflict_count": analyzer.get_conflict_count(),
        "non_conflicting_count": analyzer.get_non_conflicting_count(),
        "verification_order": analyzer.get_verification_order(),
        "asymmetry_holds": analyzer.verify_asymmetry(),
        "chain_fingerprint": fingerprint,
    }

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
