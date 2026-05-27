"""
Authentication log parser for MAC chain verification system.

Parses the structured auth log format and produces typed event records
for downstream processing by the chain state machine.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class AuthEvent:
    """Represents a single authentication event in the MAC chain system."""
    timestamp: int
    authority: str
    msg_type: str  # SIGN, BATCH, SYNC
    payload: Dict[str, str] = field(default_factory=dict)
    peer_chain: Optional[Dict[str, int]] = None
    msg_id: Optional[str] = None
    source: Optional[str] = None  # For SYNC: peer authority
    cost: int = 1


def parse_payload(raw_payload: str) -> Dict[str, str]:
    """Parse a comma-separated key=value payload string into a dictionary.

    Handles the special case where peer_chain contains colons and commas
    by treating everything after 'peer_chain=' as the chain string.
    """
    result = {}
    pc_marker = "peer_chain="
    pc_idx = raw_payload.find(pc_marker)

    if pc_idx >= 0:
        # Split into pre-chain and chain portions
        pre_chain = raw_payload[:pc_idx].rstrip(",")
        chain_str = raw_payload[pc_idx + len(pc_marker):]

        # Parse pre-chain key=value pairs
        for part in pre_chain.split(","):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                result[k] = v

        # Store raw chain string for later parsing
        result["peer_chain"] = chain_str
    else:
        # Simple key=value parsing
        for part in raw_payload.split(","):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                result[k] = v

    return result


def parse_peer_chain(chain_str: str) -> Dict[str, int]:
    """Parse a peer chain string like 'auth_alpha:7,auth_beta:3' into a dict."""
    state = {}
    for component in chain_str.split(","):
        component = component.strip()
        if ":" in component:
            auth, val = component.split(":", 1)
            state[auth] = int(val)
    return state


def parse_auth_log(filepath: str) -> List[AuthEvent]:
    """Parse an authentication log file and return a list of AuthEvent objects.

    Events are returned in file order (which should be sorted by timestamp
    for well-formed logs, but the parser does not enforce this).
    """
    events = []

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Auth log not found: {filepath}")

    with open(filepath, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            parts = line.split("|")
            if len(parts) != 4:
                raise ValueError(
                    f"Malformed event at line {line_num}: expected 4 pipe-delimited fields, "
                    f"got {len(parts)}"
                )

            timestamp_str, authority, msg_type, raw_payload = parts

            # Validate timestamp
            try:
                timestamp = int(timestamp_str)
            except ValueError:
                raise ValueError(
                    f"Invalid timestamp at line {line_num}: '{timestamp_str}'"
                )

            # Validate message type
            if msg_type not in ("SIGN", "BATCH", "SYNC"):
                raise ValueError(
                    f"Unknown message type at line {line_num}: '{msg_type}'"
                )

            # Parse payload
            payload = parse_payload(raw_payload)

            # Build event record
            event = AuthEvent(
                timestamp=timestamp,
                authority=authority,
                msg_type=msg_type,
                payload=payload,
            )

            # Extract cost
            if "cost" in payload:
                event.cost = int(payload["cost"])

            # Extract SYNC metadata
            if msg_type == "SYNC":
                event.source = payload.get("from")
                event.msg_id = payload.get("msg_id")
                if "peer_chain" in payload:
                    event.peer_chain = parse_peer_chain(payload["peer_chain"])

            events.append(event)

    # Sort by timestamp for deterministic processing order
    events.sort(key=lambda e: (e.timestamp, e.authority))

    return events


def get_authority_ids(events: List[AuthEvent]) -> List[str]:
    """Extract unique authority IDs from event list, sorted."""
    return sorted(set(e.authority for e in events))
