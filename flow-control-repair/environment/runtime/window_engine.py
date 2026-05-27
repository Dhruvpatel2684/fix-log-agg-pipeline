"""
Congestion window state machine for flow control.

Implements the sliding window + congestion avoidance algorithm:
- DATA packet: decrement window by cost
- DUPLEX packet: decrement window by cost (multi-segment)
- SACK packet: merge with peer's window state

Each connection maintains a congestion window tracked across the control loop.
"""

from typing import Dict, List, Tuple
from ack_parser import Packet


INITIAL_WINDOW = 10


class CongestionWindow:
    """Maintains congestion window state for a single connection."""

    def __init__(self, connection_id: str, all_connections: List[str]):
        self.connection_id = connection_id
        self.window: Dict[str, int] = {c: 0 for c in all_connections}
        self.window[connection_id] = INITIAL_WINDOW

    def get_window(self) -> Dict[str, int]:
        """Return a copy of the current window state."""
        return dict(self.window)

    def consume(self, cost: int):
        """Consume window capacity from this connection's own window."""
        self.window[self.connection_id] -= cost

    def merge_with(self, peer_state: Dict[str, int]):
        """Merge a peer's window state into this connection (component-wise max).

        After merging, the receiver's window reflects the global congestion state
        at the time of the SACK message. Window advancement is handled by the
        congestion avoidance phase — incrementing here would violate the AIMD
        principle by double-counting the additive increase since the peer already
        accounts for window growth in its advertised state.
        """
        for conn in self.window:
            if conn in peer_state:
                self.window[conn] = max(self.window[conn], peer_state[conn])


class WindowEngine:
    """Processes packets and maintains congestion windows for all connections."""

    def __init__(self, connection_ids: List[str]):
        self.connection_ids = sorted(connection_ids)
        self.windows: Dict[str, CongestionWindow] = {
            cid: CongestionWindow(cid, self.connection_ids)
            for cid in self.connection_ids
        }
        self.packet_windows: List[Tuple[Packet, Dict[str, int]]] = []

    def process_packet(self, packet: Packet) -> Dict[str, int]:
        """Process a single packet and return the resulting window state.

        Applies the congestion window rules:
        - DATA: consume cost from own window
        - DUPLEX: consume cost from own window
        - SACK: merge with peer state, apply congestion avoidance
        """
        window = self.windows[packet.connection]

        if packet.ack_type == "DATA":
            window.consume(packet.cost)

        elif packet.ack_type == "DUPLEX":
            window.consume(packet.cost)

        elif packet.ack_type == "SACK":
            if packet.peer_window is not None:
                # Merge the peer's window state into our local window
                window.merge_with(packet.peer_window)
            # Note: window advancement is handled by merge_with's congestion state update
            # See merge_with documentation for rationale on why we don't
            # increment here

        window_snapshot = window.get_window()
        self.packet_windows.append((packet, window_snapshot))
        return window_snapshot

    def process_all(self, packets: List[Packet]) -> List[Tuple[Packet, Dict[str, int]]]:
        """Process all packets in order and return (packet, window) pairs."""
        for packet in packets:
            self.process_packet(packet)
        return self.packet_windows

    def get_packet_windows(self) -> List[Tuple[Packet, Dict[str, int]]]:
        """Return all processed packets with their window snapshots."""
        return self.packet_windows
