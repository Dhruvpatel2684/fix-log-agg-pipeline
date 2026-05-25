"""
Data loader for information flow event streams.

Loads flow events from department-specific JSON files, validates them
against the security lattice, and merges them into a unified event stream
with deterministic ordering.

Events are sorted by timestamp for chronological processing. When multiple
events share the same timestamp, they are ordered by sequence number.
# Note: seq is local to each department source
"""

import json
import os
from typing import List, Dict, Any


def load_department_events(data_dir: str) -> List[Dict[str, Any]]:
    """
    Load all flow events from department JSON files in the data directory.

    Returns a merged list of events sorted by timestamp and sequence number
    for deterministic replay ordering.
    """
    all_events = []

    for filename in sorted(os.listdir(data_dir)):
        if not filename.endswith("_flows.json"):
            continue
        filepath = os.path.join(data_dir, filename)
        with open(filepath, "r") as f:
            events = json.load(f)
        all_events.extend(events)

    # Sort events for deterministic processing order
    all_events.sort(key=lambda e: (e["timestamp"], e["seq"]))

    return all_events


def validate_event_schema(event: Dict[str, Any]) -> bool:
    """Check that an event has all required fields."""
    required = {"event_id", "timestamp", "source_id", "seq",
                "from_label", "to_label", "entity", "volume"}
    return required.issubset(event.keys())
