"""
Request log parser for rate-limiting system traces.

Parses the structured request log format and produces typed request records
for downstream processing by the token bucket state machine.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class Request:
    """Represents a single request in the rate-limiting system."""
    timestamp: int
    service: str
    request_type: str  # INBOUND, BURST, REFILL
    payload: Dict[str, str] = field(default_factory=dict)
    token_state: Optional[Dict[str, int]] = None
    msg_id: Optional[str] = None
    source: Optional[str] = None  # For REFILL: upstream service
    cost: int = 1


def parse_payload(raw_payload: str) -> Dict[str, str]:
    """Parse a comma-separated key=value payload string into a dictionary.

    Handles the special case where token_state contains colons and commas
    by treating everything after 'token_state=' as the state string.
    """
    result = {}
    ts_marker = "token_state="
    ts_idx = raw_payload.find(ts_marker)

    if ts_idx >= 0:
        # Split into pre-state and state portions
        pre_state = raw_payload[:ts_idx].rstrip(",")
        state_str = raw_payload[ts_idx + len(ts_marker):]

        # Parse pre-state key=value pairs
        for part in pre_state.split(","):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                result[k] = v

        # Store raw state string for later parsing
        result["token_state"] = state_str
    else:
        # Simple key=value parsing
        for part in raw_payload.split(","):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                result[k] = v

    return result


def parse_token_state(state_str: str) -> Dict[str, int]:
    """Parse a token state string like 'svc_alpha:7,svc_beta:3' into a dict."""
    state = {}
    for component in state_str.split(","):
        component = component.strip()
        if ":" in component:
            svc, val = component.split(":", 1)
            state[svc] = int(val)
    return state


def parse_request_log(filepath: str) -> List[Request]:
    """Parse a request log file and return a list of Request objects.

    Requests are returned in file order (which should be sorted by timestamp
    for well-formed logs, but the parser does not enforce this).
    """
    requests = []

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Request log not found: {filepath}")

    with open(filepath, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            parts = line.split("|")
            if len(parts) != 4:
                raise ValueError(
                    f"Malformed request at line {line_num}: expected 4 pipe-delimited fields, "
                    f"got {len(parts)}"
                )

            timestamp_str, service, request_type, raw_payload = parts

            # Validate timestamp
            try:
                timestamp = int(timestamp_str)
            except ValueError:
                raise ValueError(
                    f"Invalid timestamp at line {line_num}: '{timestamp_str}'"
                )

            # Validate request type
            if request_type not in ("INBOUND", "BURST", "REFILL"):
                raise ValueError(
                    f"Unknown request type at line {line_num}: '{request_type}'"
                )

            # Parse payload
            payload = parse_payload(raw_payload)

            # Build request record
            request = Request(
                timestamp=timestamp,
                service=service,
                request_type=request_type,
                payload=payload,
            )

            # Extract cost
            if "cost" in payload:
                request.cost = int(payload["cost"])

            # Extract REFILL metadata
            if request_type == "REFILL":
                request.source = payload.get("from")
                request.msg_id = payload.get("msg_id")
                if "token_state" in payload:
                    request.token_state = parse_token_state(payload["token_state"])

            requests.append(request)

    # Sort by timestamp for deterministic processing order
    requests.sort(key=lambda r: (r.timestamp, r.service))

    return requests


def get_service_ids(requests: List[Request]) -> List[str]:
    """Extract unique service IDs from request list, sorted."""
    return sorted(set(r.service for r in requests))
