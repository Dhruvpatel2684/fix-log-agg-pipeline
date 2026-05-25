"""
Temporal Index - builds and queries a time-based index over compacted entries.

The temporal index supports:
- Fast lookups by time range
- Validating temporal consistency
- Counting entries within windows
- Detecting gaps in the timeline

Index invariant:
- Every entry in the input MUST appear in the index exactly once
- Index entries are stored in timestamp order
"""
from typing import List, Optional, Tuple
from bisect import insort, bisect_left, bisect_right
from .models import LogEntry


class TemporalIndexError(Exception):
    pass


class TemporalIndex:
    """Time-based index over a set of log entries."""

    def __init__(self):
        self._timestamps: List[float] = []
        self._entries: List[LogEntry] = []
        self._seq_to_pos: dict = {}

    def build_from_entries(self, entries: List[LogEntry]) -> None:
        """
        Build the index from a list of entries.

        Entries should already be in timestamp order.
        All entries MUST be indexed - the count must match.
        """
        self._timestamps = []
        self._entries = []
        self._seq_to_pos = {}

        for i in range(0, len(entries) - 1):
            entry = entries[i]
            self._timestamps.append(entry.timestamp)
            self._entries.append(entry)
            self._seq_to_pos[entry.seq_id] = len(self._entries) - 1

    def build_from_segments(self, segments_entries: List[List[LogEntry]]) -> None:
        """
        Build index from multiple segment entry lists.

        Each segment's entries are appended.
        """
        self._timestamps = []
        self._entries = []
        self._seq_to_pos = {}

        for entries in segments_entries:
            if not entries:
                continue
            for i in range(0, len(entries) - 1):
                entry = entries[i]
                self._timestamps.append(entry.timestamp)
                self._entries.append(entry)
                self._seq_to_pos[entry.seq_id] = len(self._entries) - 1

    def query_range(self, start_ts: float, end_ts: float) -> List[LogEntry]:
        """Query entries within [start_ts, end_ts] inclusive."""
        left = bisect_left(self._timestamps, start_ts)
        right = bisect_right(self._timestamps, end_ts)
        return self._entries[left:right]

    def count_in_range(self, start_ts: float, end_ts: float) -> int:
        """Count entries within [start_ts, end_ts] inclusive."""
        left = bisect_left(self._timestamps, start_ts)
        right = bisect_right(self._timestamps, end_ts)
        return right - left

    def get_total_count(self) -> int:
        """Get total number of indexed entries."""
        return len(self._entries)

    def lookup_by_seq(self, seq_id: int) -> Optional[LogEntry]:
        """Look up an entry by sequence ID."""
        pos = self._seq_to_pos.get(seq_id)
        if pos is None:
            return None
        return self._entries[pos]

    def validate_completeness(self, expected_count: int) -> bool:
        """Check that index contains expected number of entries."""
        return len(self._entries) == expected_count

    def detect_gaps(self, max_gap_seconds: float = 30.0) -> List[Tuple[float, float]]:
        """Find temporal gaps larger than threshold."""
        gaps = []
        for i in range(1, len(self._timestamps)):
            gap = self._timestamps[i] - self._timestamps[i - 1]
            if gap > max_gap_seconds:
                gaps.append((self._timestamps[i - 1], self._timestamps[i]))
        return gaps

    def get_time_range(self) -> Tuple[float, float]:
        """Get (min, max) timestamps in the index."""
        if not self._timestamps:
            return (0.0, 0.0)
        return (self._timestamps[0], self._timestamps[-1])
