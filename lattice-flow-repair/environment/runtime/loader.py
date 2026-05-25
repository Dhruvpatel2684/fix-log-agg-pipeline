"""
Data loader for multi-dimensional information flow event streams.

Loads flow events from source-specific JSON files, validates them,
merges them into a unified event stream, and performs deduplication
of events that represent the same underlying information transfer.

Events are sorted by timestamp for chronological processing. When
multiple events share the same timestamp, ordering is determined by
source identifier and then by the local sequence number within that
source stream.
"""

import json
import os
from typing import List, Dict, Any, Set, Tuple


def load_source_events(data_dir: str) -> List[Dict[str, Any]]:
    """
    Load all flow events from source JSON files in the data directory.

    Returns a merged list of events sorted by timestamp, source_id,
    and sequence number for deterministic replay ordering.
    """
    all_events = []

    for filename in sorted(os.listdir(data_dir)):
        if not filename.endswith("_flows.json"):
            continue
        filepath = os.path.join(data_dir, filename)
        with open(filepath, "r") as f:
            events = json.load(f)
        all_events.extend(events)

    # Sort for deterministic chronological ordering
    all_events.sort(key=lambda e: (e["timestamp"], e["source_id"], e["seq"]))

    return all_events


def deduplicate_events(
    events: List[Dict[str, Any]], window_seconds: int
) -> List[Dict[str, Any]]:
    """
    Remove duplicate events within a time window.

    Two events are considered duplicates if they reference the same entity
    and occur within the deduplication window. This handles cases where
    the same information flow is reported by multiple upstream sensors.

    When duplicates are found, only the first occurrence (by sort order)
    is retained.
    """
    from datetime import datetime

    seen: Set[Tuple[str, str]] = set()
    result = []

    for event in events:
        # Deduplication key: entity within a time bucket
        ts = datetime.fromisoformat(event["timestamp"])
        bucket = int(ts.timestamp()) // window_seconds
        dedup_key = (event["entity"], str(bucket))

        if dedup_key not in seen:
            seen.add(dedup_key)
            result.append(event)

    return result


def validate_event_schema(event: Dict[str, Any]) -> bool:
    """Check that an event has all required fields for product lattice analysis."""
    required = {
        "event_id", "timestamp", "source_id", "seq", "entity",
        "from_conf", "from_integ", "to_conf", "to_integ", "volume"
    }
    return required.issubset(event.keys())
