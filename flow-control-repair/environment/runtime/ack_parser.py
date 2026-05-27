"""
ACK log parser for flow control system traces.

Parses the structured ACK log format and produces typed packet records
for downstream processing by the window state machine.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional, Dict


@dataclass
class Packet:
    """Represents a single packet acknowledgment in the flow control system."""
    timestamp: int
    connection: str
    ack_type: str  # DATA, DUPLEX, SACK
    payload: Dict[str, str] = field(default_factory=dict)
    peer_window: Optional[Dict[str, int]] = None
    msg_id: Optional[str] = None
    source: Optional[str] = None  # For SACK: peer connection
    cost: int = 1


def parse_payload(raw_payload: str) -> Dict[str, str]:
    """Parse a comma-separated key=value payload string into a dictionary.

    Handles the special case where peer_window contains colons and commas
    by treating everything after 'peer_window=' as the window string.
    """
    result = {}
    pw_marker = "peer_window="
    pw_idx = raw_payload.find(pw_marker)

    if pw_idx >= 0:
        # Split into pre-window and window portions
        pre_window = raw_payload[:pw_idx].rstrip(",")
        window_str = raw_payload[pw_idx + len(pw_marker):]

        # Parse pre-window key=value pairs
        for part in pre_window.split(","):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                result[k] = v

        # Store raw window string for later parsing
        result["peer_window"] = window_str
    else:
        # Simple key=value parsing
        for part in raw_payload.split(","):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                result[k] = v

    return result


def parse_peer_window(window_str: str) -> Dict[str, int]:
    """Parse a peer window string like 'conn_alpha:7,conn_beta:3' into a dict."""
    state = {}
    for component in window_str.split(","):
        component = component.strip()
        if ":" in component:
            conn, val = component.split(":", 1)
            state[conn] = int(val)
    return state


def parse_ack_log(filepath: str) -> List[Packet]:
    """Parse an ACK log file and return a list of Packet objects.

    Packets are returned in file order (which should be sorted by timestamp
    for well-formed logs, but the parser does not enforce this).
    """
    packets = []

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"ACK log not found: {filepath}")

    with open(filepath, "r") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            parts = line.split("|")
            if len(parts) != 4:
                raise ValueError(
                    f"Malformed packet at line {line_num}: expected 4 pipe-delimited fields, "
                    f"got {len(parts)}"
                )

            timestamp_str, connection, ack_type, raw_payload = parts

            # Validate timestamp
            try:
                timestamp = int(timestamp_str)
            except ValueError:
                raise ValueError(
                    f"Invalid timestamp at line {line_num}: '{timestamp_str}'"
                )

            # Validate ACK type
            if ack_type not in ("DATA", "DUPLEX", "SACK"):
                raise ValueError(
                    f"Unknown ACK type at line {line_num}: '{ack_type}'"
                )

            # Parse payload
            payload = parse_payload(raw_payload)

            # Build packet record
            packet = Packet(
                timestamp=timestamp,
                connection=connection,
                ack_type=ack_type,
                payload=payload,
            )

            # Extract cost
            if "cost" in payload:
                packet.cost = int(payload["cost"])

            # Extract SACK metadata
            if ack_type == "SACK":
                packet.source = payload.get("from")
                packet.msg_id = payload.get("msg_id")
                if "peer_window" in payload:
                    packet.peer_window = parse_peer_window(payload["peer_window"])

            packets.append(packet)

    # Sort by timestamp for deterministic processing order
    packets.sort(key=lambda p: (p.timestamp, p.connection))

    return packets


def get_connection_ids(packets: List[Packet]) -> List[str]:
    """Extract unique connection IDs from packet list, sorted."""
    return sorted(set(p.connection for p in packets))
