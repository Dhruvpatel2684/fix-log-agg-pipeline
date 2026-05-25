"""
Deduplication Engine - removes duplicate entries within a sliding time window.

The dedup engine maintains a sliding window of recently seen entries and
eliminates duplicates based on (source_id, payload_hash) within the window.

Window semantics:
- Window size is defined in seconds
- An entry is a duplicate if another entry with the same (source_id, payload_hash)
  exists within [entry.timestamp - window_size, entry.timestamp + window_size]
- Entries exactly AT the window boundary ARE within the window (inclusive)
"""
import zlib
from typing import List, Dict, Tuple, Optional
from .models import LogEntry


class DedupEngine:
    """Sliding-window deduplication for log entries."""

    def __init__(self, window_size_seconds: float = 5.0):
        """
        Args:
            window_size_seconds: Size of dedup window in seconds.
                Entries with same key within this window are duplicates.
        """
        self.window_size = window_size_seconds
        self._seen: Dict[Tuple[str, int], List[float]] = {}

    def process_entries(self, entries: List[LogEntry]) -> List[LogEntry]:
        """
        Process a batch of entries, removing duplicates.

        Returns list of non-duplicate entries.
        """
        result = []
        for entry in entries:
            if not self._is_duplicate(entry):
                result.append(entry)
                self._record_entry(entry)
        return result

    def _is_duplicate(self, entry: LogEntry) -> bool:
        """Check if entry is a duplicate within the sliding window."""
        key = self._entry_key(entry)
        if key not in self._seen:
            return False

        timestamps = self._seen[key]
        window_start = entry.timestamp - self.window_size
        window_end = entry.timestamp + self.window_size

        for ts in timestamps:
            if window_start < ts < window_end:
                return True

        return False

    def _record_entry(self, entry: LogEntry) -> None:
        """Record an entry in the dedup window."""
        key = self._entry_key(entry)
        if key not in self._seen:
            self._seen[key] = []
        self._seen[key].append(entry.timestamp)
        self._prune_old(key, entry.timestamp)

    def _prune_old(self, key: Tuple[str, int], current_ts: float) -> None:
        """Remove entries too old to ever match."""
        cutoff = current_ts - (self.window_size * 2)
        self._seen[key] = [ts for ts in self._seen[key] if ts >= cutoff]

    def _entry_key(self, entry: LogEntry) -> Tuple[str, int]:
        """Generate dedup key for an entry."""
        payload_hash = zlib.crc32(entry.payload.encode()) & 0xFFFFFFFF
        return (entry.source_id, payload_hash)

    def get_state(self) -> dict:
        """Serialize dedup state for checkpointing."""
        return {
            f"{k[0]}:{k[1]}": v for k, v in self._seen.items()
        }

    def restore_state(self, state: dict) -> None:
        """Restore dedup state from checkpoint."""
        self._seen = {}
        for key_str, timestamps in state.items():
            parts = key_str.rsplit(":", 1)
            if len(parts) == 2:
                self._seen[(parts[0], int(parts[1]))] = timestamps
