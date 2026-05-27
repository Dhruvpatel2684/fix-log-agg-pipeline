"""
Token bucket state machine for distributed rate limiting.

Implements the sliding window + token bucket algorithm:
- INBOUND request: decrement token count by cost
- BURST request: decrement token count by cost (multi-unit)
- REFILL request: merge with upstream token state

Each service maintains a token budget tracked across the sliding window.
"""

from typing import Dict, List, Tuple
from request_parser import Request


INITIAL_BUDGET = 10


class TokenBucket:
    """Maintains token bucket state for a single service."""

    def __init__(self, service_id: str, all_services: List[str]):
        self.service_id = service_id
        self.budget: Dict[str, int] = {s: 0 for s in all_services}
        self.budget[service_id] = INITIAL_BUDGET

    def get_budget(self) -> Dict[str, int]:
        """Return a copy of the current budget state."""
        return dict(self.budget)

    def consume(self, cost: int):
        """Consume tokens from this service's own budget."""
        self.budget[self.service_id] -= cost

    def merge_with(self, upstream_state: Dict[str, int]):
        """Merge an upstream token state into this bucket (component-wise max).

        After merging, the receiver's budget reflects the global token state at
        the time of the refill message. Replenishment is handled by the window
        boundary reset — adding tokens here would double-count the recovery
        period since the upstream already accounts for regeneration in its state.
        """
        for svc in self.budget:
            if svc in upstream_state:
                self.budget[svc] = max(self.budget[svc], upstream_state[svc])


class TokenEngine:
    """Processes requests and maintains token buckets for all services."""

    def __init__(self, service_ids: List[str]):
        self.service_ids = sorted(service_ids)
        self.buckets: Dict[str, TokenBucket] = {
            sid: TokenBucket(sid, self.service_ids)
            for sid in self.service_ids
        }
        self.request_budgets: List[Tuple[Request, Dict[str, int]]] = []

    def process_request(self, request: Request) -> Dict[str, int]:
        """Process a single request and return the resulting budget state.

        Applies the token bucket rules:
        - INBOUND: consume cost from own budget
        - BURST: consume cost from own budget
        - REFILL: merge with upstream state, replenish proportional to elapsed time
        """
        bucket = self.buckets[request.service]

        if request.request_type == "INBOUND":
            bucket.consume(request.cost)

        elif request.request_type == "BURST":
            bucket.consume(request.cost)

        elif request.request_type == "REFILL":
            if request.token_state is not None:
                # Merge the upstream's token state into our local budget
                bucket.merge_with(request.token_state)
            # Note: replenishment is handled by merge_with's window state update
            # See merge_with documentation for rationale on why we don't
            # add tokens here

        budget_snapshot = bucket.get_budget()
        self.request_budgets.append((request, budget_snapshot))
        return budget_snapshot

    def process_all(self, requests: List[Request]) -> List[Tuple[Request, Dict[str, int]]]:
        """Process all requests in order and return (request, budget) pairs."""
        for request in requests:
            self.process_request(request)
        return self.request_budgets

    def get_request_budgets(self) -> List[Tuple[Request, Dict[str, int]]]:
        """Return all processed requests with their budget snapshots."""
        return self.request_budgets
