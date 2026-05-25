"""
Tests for temporal ordering invariants.

The compaction pipeline must produce output where entries are ordered
by timestamp (ascending). This is a fundamental invariant for downstream
consumers that depend on temporal monotonicity.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "environment"))

from src.models import LogEntry, WALSegment
from src.merger import SegmentMerger
from src.wal_reader import WALReader
from src.compactor import IncrementalCompactor


class TestMergerTemporalOrdering:
    def test_merge_preserves_timestamp_order_across_sources(self, loaded_segments):
        """
        When merging segments from different sources, output must be
        ordered by timestamp regardless of original seq_id assignment.
        """
        merger = SegmentMerger()
        merged = merger.merge_segments(loaded_segments)

        for i in range(1, len(merged)):
            assert merged[i].timestamp >= merged[i - 1].timestamp, (
                f"Temporal monotonicity violated at position {i}: "
                f"ts={merged[i].timestamp} < prev_ts={merged[i-1].timestamp} "
                f"(entry from {merged[i].source_id}, seq={merged[i].seq_id})"
            )

    def test_merge_tiebreaks_by_seq_for_equal_timestamps(self):
        """When timestamps are equal, entries should be ordered by seq_id."""
        merger = SegmentMerger()

        seg_a = WALSegment(
            segment_id="seg_a", source_id="src_a",
            entries=[
                LogEntry(seq_id=5, timestamp=100.0, source_id="src_a", payload="a1"),
                LogEntry(seq_id=2, timestamp=100.0, source_id="src_a", payload="a2"),
            ]
        )
        seg_b = WALSegment(
            segment_id="seg_b", source_id="src_b",
            entries=[
                LogEntry(seq_id=3, timestamp=100.0, source_id="src_b", payload="b1"),
                LogEntry(seq_id=7, timestamp=100.0, source_id="src_b", payload="b2"),
            ]
        )

        merged = merger.merge_segments([seg_a, seg_b])
        seq_ids = [e.seq_id for e in merged]
        assert seq_ids == sorted(seq_ids), f"Tiebreaker ordering failed: got {seq_ids}"

    def test_merge_interleaved_sources_correct_order(self, fresh_segments):
        """
        Segments from node-alpha (ts 1000-1012) and node-beta (ts 1001-1014)
        must be interleaved correctly by timestamp in output.
        """
        merger = SegmentMerger()
        merged = merger.merge_segments(fresh_segments)

        assert merged[0].timestamp == 1000.0, (
            f"Expected first entry at ts=1000.0, got ts={merged[0].timestamp}"
        )

        violations = []
        for i in range(1, len(merged)):
            if merged[i].timestamp < merged[i - 1].timestamp:
                violations.append(
                    f"pos {i}: {merged[i].timestamp} < {merged[i-1].timestamp}"
                )
        assert not violations, (
            f"Found {len(violations)} temporal ordering violations: "
            + "; ".join(violations[:5])
        )


class TestCompactedOutputOrdering:
    def test_fresh_compaction_temporal_monotonicity(
        self, fresh_segments_dir, tmp_checkpoint_dir, tmp_output_dir
    ):
        """
        A fresh compaction (no checkpoint) of multi-source segments
        must produce temporally monotonic output.
        """
        compactor = IncrementalCompactor(
            segments_dir=fresh_segments_dir,
            checkpoint_dir=tmp_checkpoint_dir,
            output_dir=tmp_output_dir,
            dedup_window=5.0,
        )
        output = compactor.run_compaction()

        assert len(output.entries) > 0, "Compaction produced no entries"

        for i in range(1, len(output.entries)):
            assert output.entries[i].timestamp >= output.entries[i - 1].timestamp, (
                f"Compacted output violates temporal monotonicity at pos {i}: "
                f"{output.entries[i].timestamp} < {output.entries[i-1].timestamp}"
            )
