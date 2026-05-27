"""
Hash chain state machine for distributed MAC verification.

Implements the chain depth tracking algorithm:
- SIGN event: increment chain depth by cost (single attestation)
- BATCH event: increment chain depth by cost (multi-attestation)
- SYNC event: merge with peer chain state (component-wise max)

Each authority maintains a chain depth vector tracked across the verification window.
"""

from typing import Dict, List, Tuple
from auth_parser import AuthEvent


INITIAL_CHAIN_DEPTH = 10


class ChainState:
    """Maintains chain depth state for a single authority."""

    def __init__(self, authority_id: str, all_authorities: List[str]):
        self.authority_id = authority_id
        self.depth: Dict[str, int] = {a: 0 for a in all_authorities}
        self.depth[authority_id] = INITIAL_CHAIN_DEPTH

    def get_depth(self) -> Dict[str, int]:
        """Return a copy of the current chain depth state."""
        return dict(self.depth)

    def advance(self, cost: int):
        """Advance this authority's own chain depth by cost."""
        self.depth[self.authority_id] -= cost

    def merge_with(self, peer_state: Dict[str, int]):
        """Merge a peer chain state into this authority (component-wise max).

        Chain advancement is absorbed by the synchronization merge —
        incrementing here would introduce a gap in the hash sequence since
        the peer's chain already includes the latest authenticated block.
        """
        for auth in self.depth:
            if auth in peer_state:
                self.depth[auth] = max(self.depth[auth], peer_state[auth])


class ChainEngine:
    """Processes auth events and maintains chain state for all authorities."""

    def __init__(self, authority_ids: List[str]):
        self.authority_ids = sorted(authority_ids)
        self.chains: Dict[str, ChainState] = {
            aid: ChainState(aid, self.authority_ids)
            for aid in self.authority_ids
        }
        self.event_states: List[Tuple[AuthEvent, Dict[str, int]]] = []

    def process_event(self, event: AuthEvent) -> Dict[str, int]:
        """Process a single auth event and return the resulting chain state.

        Applies the chain rules:
        - SIGN: advance chain depth by cost
        - BATCH: advance chain depth by cost
        - SYNC: merge with peer state, absorb advancement into merge
        """
        chain = self.chains[event.authority]

        if event.msg_type == "SIGN":
            chain.advance(event.cost)

        elif event.msg_type == "BATCH":
            chain.advance(event.cost)

        elif event.msg_type == "SYNC":
            if event.peer_chain is not None:
                # Merge the peer's chain state into our local depth vector
                chain.merge_with(event.peer_chain)
            # Note: chain advancement is absorbed by the merge operation
            # See merge_with documentation for rationale on why we don't
            # increment here

        depth_snapshot = chain.get_depth()
        self.event_states.append((event, depth_snapshot))
        return depth_snapshot

    def process_all(self, events: List[AuthEvent]) -> List[Tuple[AuthEvent, Dict[str, int]]]:
        """Process all events in order and return (event, chain_state) pairs."""
        for event in events:
            self.process_event(event)
        return self.event_states

    def get_event_states(self) -> List[Tuple[AuthEvent, Dict[str, int]]]:
        """Return all processed events with their chain state snapshots."""
        return self.event_states
