"""
Tests for deduplication consistency.

The dedup engine must correctly identify duplicates within the configured
time window. Window boundaries are INCLUSIVE - entries exactly at the
boundary distance are within the window.
"""
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "environment"))

from src.models import LogEntry, WALSegment
from src.dedup_engine import DedupEngine
from src.compactor import IncrementalCompactor


class TestDedupWindowBoundary:
    def test_exact_boundary_is_duplicate(self):
        """
        An entry with the same (source_id, payload) exactly at the window
        boundary distance IS a duplicate and must be removed.

        Window size = 5.0s means entries within [t-5.0, t+5.0] INCLUSIVE
        are considered duplicates.
        """
        dedup = DedupEngine(window_size_seconds=5.0)

        entries = [
            LogEntry(seq_id=1, timestamp=1000.0, source_id="src-a",
                     payload="duplicate message"),
            LogEntry(seq_id=2, timestamp=1005.0, source_id="src-a",
                     payload="duplicate message"),
        ]

        result = dedup.process_entries(entries)

        assert len(result) == 1, (
            f"Expected 1 entry (boundary duplicate removed), got {len(result)}. "
            f"Window boundary should be inclusive."
        )
        assert result[0].seq_id == 1

    def test_just_outside_boundary_is_not_duplicate(self):
        """Entry just barely outside the window is NOT a duplicate."""
        dedup = DedupEngine(window_size_seconds=5.0)

        entries = [
            LogEntry(seq_id=1, timestamp=1000.0, source_id="src-a",
                     payload="not a dup"),
            LogEntry(seq_id=2, timestamp=1005.01, source_id="src-a",
                     payload="not a dup"),
        ]

        result = dedup.process_entries(entries)
        assert len(result) == 2, (
            f"Expected 2 entries (outside boundary), got {len(result)}"
        )

    def test_dedup_in_full_pipeline_catches_boundary(
        self, fresh_segments_dir, tmp_checkpoint_dir, tmp_output_dir
    ):
        """
        The full compaction pipeline must catch duplicates at exact
        window boundaries. In our fixture data, entry 3 (ts=1005.0,
        payload='listener started on port 8080') and entry 13 (ts=1010.0,
        same payload, same source) are exactly 5.0s apart - a duplicate.
        """
        compactor = IncrementalCompactor(
            segments_dir=fresh_segments_dir,
            checkpoint_dir=tmp_checkpoint_dir,
            output_dir=tmp_output_dir,
            dedup_window=5.0,
        )
        output = compactor.run_compaction()

        dup_payload = "listener started on port 8080"
        matching = [e for e in output.entries if e.payload == dup_payload]

        assert len(matching) == 1, (
            f"Expected exactly 1 entry with payload '{dup_payload}' "
            f"(duplicate at boundary should be removed), got {len(matching)}"
        )

    def test_different_source_same_payload_not_duplicate(self):
        """Entries from different sources with same payload are NOT duplicates."""
        dedup = DedupEngine(window_size_seconds=5.0)

        entries = [
            LogEntry(seq_id=1, timestamp=1000.0, source_id="src-a",
                     payload="shared message"),
            LogEntry(seq_id=2, timestamp=1002.0, source_id="src-b",
                     payload="shared message"),
        ]

        result = dedup.process_entries(entries)
        assert len(result) == 2, "Different sources should not be deduplicated"
