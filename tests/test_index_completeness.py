"""
Tests for temporal index completeness and correctness.

The temporal index must contain ALL entries that were compacted.
Missing entries indicate data loss in the indexing layer.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "environment"))

from src.models import LogEntry, WALSegment
from src.temporal_index import TemporalIndex
from src.compactor import IncrementalCompactor


class TestIndexCompleteness:
    def test_index_count_matches_input(self):
        """
        The number of entries in the index must exactly match the
        number of input entries.
        """
        index = TemporalIndex()
        entries = [
            LogEntry(seq_id=i, timestamp=1000.0 + i * 0.5,
                     source_id="src", payload=f"msg_{i}")
            for i in range(1, 21)
        ]

        index.build_from_entries(entries)

        assert index.get_total_count() == len(entries), (
            f"Index has {index.get_total_count()} entries but input had "
            f"{len(entries)}. Missing entries indicate indexing data loss."
        )

    def test_all_entries_queryable_by_seq(self):
        """Every input entry must be retrievable by its sequence ID."""
        index = TemporalIndex()
        entries = [
            LogEntry(seq_id=i, timestamp=1000.0 + i,
                     source_id="src", payload=f"entry_{i}")
            for i in range(1, 16)
        ]

        index.build_from_entries(entries)

        missing = []
        for entry in entries:
            result = index.lookup_by_seq(entry.seq_id)
            if result is None:
                missing.append(entry.seq_id)

        assert not missing, (
            f"Entries with seq_ids {missing} are not in the index. "
            f"The index is missing entries from the input."
        )

    def test_last_entry_is_indexed(self):
        """The LAST entry of the input must be in the index."""
        index = TemporalIndex()
        entries = [
            LogEntry(seq_id=i, timestamp=1000.0 + i,
                     source_id="src", payload=f"item_{i}")
            for i in range(1, 11)
        ]

        index.build_from_entries(entries)

        last_entry = entries[-1]
        result = index.lookup_by_seq(last_entry.seq_id)

        assert result is not None, (
            f"Last entry (seq_id={last_entry.seq_id}) is missing from index. "
            f"Index has {index.get_total_count()} of {len(entries)} entries."
        )
        assert result.payload == last_entry.payload

    def test_multi_segment_index_completeness(self):
        """
        When building index from multiple segment entry lists,
        ALL entries from ALL segments must be included.
        """
        index = TemporalIndex()

        seg1_entries = [
            LogEntry(seq_id=i, timestamp=1000.0 + i,
                     source_id="a", payload=f"seg1_{i}")
            for i in range(1, 8)
        ]
        seg2_entries = [
            LogEntry(seq_id=i + 10, timestamp=2000.0 + i,
                     source_id="b", payload=f"seg2_{i}")
            for i in range(1, 6)
        ]

        index.build_from_segments([seg1_entries, seg2_entries])

        total_input = len(seg1_entries) + len(seg2_entries)
        assert index.get_total_count() == total_input, (
            f"Multi-segment index has {index.get_total_count()} entries "
            f"but input had {total_input} total. "
            f"Segment boundary handling may be dropping entries."
        )

    def test_compaction_index_matches_output(
        self, fresh_segments_dir, tmp_checkpoint_dir, tmp_output_dir
    ):
        """
        After full compaction, the temporal index entry count must
        match the compaction output entry count.
        """
        compactor = IncrementalCompactor(
            segments_dir=fresh_segments_dir,
            checkpoint_dir=tmp_checkpoint_dir,
            output_dir=tmp_output_dir,
            dedup_window=5.0,
        )
        output = compactor.run_compaction()

        assert output.entry_count > 0, "Compaction produced no output"

        index_count = compactor.index.get_total_count()
        assert index_count == output.entry_count, (
            f"Temporal index has {index_count} entries but compaction "
            f"output has {output.entry_count}. Index is incomplete."
        )

    def test_range_query_returns_all_entries_in_window(self):
        """
        A range query spanning the entire time range must return
        all indexed entries.
        """
        index = TemporalIndex()
        entries = [
            LogEntry(seq_id=i, timestamp=1000.0 + i * 2.0,
                     source_id="src", payload=f"range_{i}")
            for i in range(1, 13)
        ]

        index.build_from_entries(entries)

        min_ts = entries[0].timestamp
        max_ts = entries[-1].timestamp
        results = index.query_range(min_ts, max_ts)

        assert len(results) == len(entries), (
            f"Full-range query returned {len(results)} entries "
            f"but index should have {len(entries)}"
        )
