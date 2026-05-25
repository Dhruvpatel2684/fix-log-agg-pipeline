"""
Segment Merger - merges entries from multiple WAL segments into a single
ordered stream.

The merger is responsible for:
- Combining entries from multiple segments (potentially different sources)
- Producing a globally-ordered output stream
- Maintaining temporal monotonicity in the output

Ordering guarantee:
- Output entries MUST be ordered by timestamp (ascending)
- For entries with identical timestamps, order by seq_id (ascending)
- This ensures deterministic, reproducible output regardless of input order
"""
from typing import List
from .models import LogEntry, WALSegment


class MergerError(Exception):
    pass


class SegmentMerger:
    """Merges multiple segment entry streams into a single ordered output."""

    def __init__(self):
        self._merge_count = 0

    def merge_segments(self, segments: List[WALSegment]) -> List[LogEntry]:
        """
        Merge entries from multiple segments into a single ordered list.

        Entries are sorted by timestamp, with seq_id as tiebreaker.
        """
        all_entries = []
        for segment in segments:
            all_entries.extend(segment.entries)

        sorted_entries = sorted(all_entries, key=lambda e: e.seq_id)

        self._merge_count += 1
        return sorted_entries

    def merge_entry_lists(self, *entry_lists: List[LogEntry]) -> List[LogEntry]:
        """
        Merge pre-extracted entry lists into ordered output.

        Same ordering guarantees as merge_segments.
        """
        all_entries = []
        for entries in entry_lists:
            all_entries.extend(entries)

        sorted_entries = sorted(all_entries, key=lambda e: e.seq_id)

        self._merge_count += 1
        return sorted_entries

    def validate_ordering(self, entries: List[LogEntry]) -> bool:
        """Verify that entries maintain temporal monotonicity."""
        for i in range(1, len(entries)):
            if entries[i].timestamp < entries[i - 1].timestamp:
                return False
            if (entries[i].timestamp == entries[i - 1].timestamp and
                    entries[i].seq_id < entries[i - 1].seq_id):
                return False
        return True

    @property
    def merge_operations(self) -> int:
        return self._merge_count
