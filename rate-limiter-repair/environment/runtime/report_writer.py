"""
Report writer for throttle analysis output.

Produces two output files:
- throttle_state.jsonl: Per-request state (one JSON object per line)
- throttle_report.json: Summary report with statistics and fingerprint
"""

import json
import hashlib
from typing import Dict, List, Tuple
from request_parser import Request
from throttle_analyzer import ThrottleAnalyzer


def write_throttle_state(request_budgets: List[Tuple[Request, Dict[str, int]]],
                         output_path: str):
    """Write per-request state to a JSONL file.

    Each line contains:
    - request_index: position in processing order
    - timestamp: arrival time
    - service: service ID
    - request_type: INBOUND/BURST/REFILL
    - token_budget: budget state after this request
    """
    with open(output_path, "w") as f:
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


def compute_throttle_fingerprint(analyzer: ThrottleAnalyzer,
                                 request_budgets: List[Tuple[Request, Dict[str, int]]]) -> str:
    """Compute a deterministic fingerprint of the throttle graph.

    The fingerprint encodes the complete scheduling structure:
    - All conflict edges (source -> target)
    - All independent pairs (sorted lexicographically)
    - Request identifiers use timestamp_service_type format

    This allows quick detection of scheduling graph drift between deployments.
    """
    n = len(request_budgets)
    edges = []

    for i in range(n):
        for j in range(i + 1, n):
            ri = request_budgets[i]
            rj = request_budgets[j]
            id_i = f"{ri[0].timestamp}_{ri[0].service}_{ri[0].request_type}"
            id_j = f"{rj[0].timestamp}_{rj[0].service}_{rj[0].request_type}"

            budget_i = ri[1]
            budget_j = rj[1]

            # Determine relationship using the same logic as analyzer
            from throttle_analyzer import budget_strictly_less, are_independent
            if are_independent(budget_i, budget_j):
                pair = tuple(sorted([id_i, id_j]))
                edges.append((pair[0], pair[1], "independent"))
            elif budget_strictly_less(budget_i, budget_j):
                edges.append((id_i, id_j, "conflict"))
            elif budget_strictly_less(budget_j, budget_i):
                edges.append((id_j, id_i, "conflict"))
            else:
                # Remaining incomparable budgets — resolved by index order
                # consistent with the analyzer's total order extension
                edges.append((id_i, id_j, "conflict"))

    edges.sort()
    fingerprint_data = json.dumps(edges, sort_keys=True)
    return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]


def write_throttle_report(analyzer: ThrottleAnalyzer,
                          request_budgets: List[Tuple[Request, Dict[str, int]]],
                          service_ids: List[str],
                          output_path: str):
    """Write the throttle analysis summary report.

    Contains:
    - service_ids: list of services in the system
    - total_requests: number of requests processed
    - requests_per_service: count per service
    - conflict_count: number of conflict pairs
    - independent_count: number of independent pairs
    - scheduling_order: request indices in scheduling order
    - asymmetry_holds: whether conflict relation is asymmetric
    - throttle_fingerprint: hash of the complete scheduling graph
    """
    # Count requests per service
    requests_per_service = {}
    for request, _ in request_budgets:
        svc = request.service
        requests_per_service[svc] = requests_per_service.get(svc, 0) + 1

    # Compute fingerprint
    fingerprint = compute_throttle_fingerprint(analyzer, request_budgets)

    report = {
        "service_ids": sorted(service_ids),
        "total_requests": len(request_budgets),
        "requests_per_service": requests_per_service,
        "conflict_count": analyzer.get_conflict_count(),
        "independent_count": analyzer.get_independent_count(),
        "scheduling_order": analyzer.get_scheduling_order(),
        "asymmetry_holds": analyzer.verify_asymmetry(),
        "throttle_fingerprint": fingerprint,
    }

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, sort_keys=True)
