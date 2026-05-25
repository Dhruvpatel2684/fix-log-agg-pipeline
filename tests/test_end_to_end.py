"""
End-to-end integration tests for the compaction pipeline.

These tests verify the system-level invariants that depend on
all components working correctly together.
"""
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "environment"))

from src.models import LogEntry, WALSegment
from src.compactor import IncrementalCompactor
from src.recovery import RecoveryManager
from src.temporal_index import TemporalIndex


class TestEndToEndCompaction:
    def test_fresh_compaction_entry_count(
        self, fresh_segments_dir, tmp_checkpoint_dir, tmp_output_dir
    ):
        """
        Fresh compaction of segments with one known duplicate must
        produce exactly (total_entries - 1) entries.

        Input: segment_001 (8 entries) + segment_002 (8 entries) = 16
        Known duplicate: entry at boundary (1 duplicate removed)
        Expected output: 15 entries
        """
        compactor = IncrementalCompactor(
            segments_dir=fresh_segments_dir,
            checkpoint_dir=tmp_checkpoint_dir,
            output_dir=tmp_output_dir,
            dedup_window=5.0,
        )
        output = compactor.run_compaction()

        assert output.entry_count == 15, (
            f"Expected 15 entries (16 input - 1 duplicate), "
            f"got {output.entry_count}. "
            f"Dropped duplicates reported: {output.dropped_duplicates}"
        )

    def test_all_invariants_hold_together(
        self, fresh_segments_dir, tmp_checkpoint_dir, tmp_output_dir
    ):
        """
        Combined invariant check: after compaction ALL of these must hold:
        1. Timestamps are monotonically non-decreasing
        2. Sequence IDs are strictly monotonically increasing
        3. No duplicate entries within dedup window
        4. Temporal index is complete
        """
        compactor = IncrementalCompactor(
            segments_dir=fresh_segments_dir,
            checkpoint_dir=tmp_checkpoint_dir,
            output_dir=tmp_output_dir,
            dedup_window=5.0,
        )
        output = compactor.run_compaction()
        entries = output.entries

        assert len(entries) > 0

        ts_violations = []
        for i in range(1, len(entries)):
            if entries[i].timestamp < entries[i - 1].timestamp:
                ts_violations.append(i)

        seq_violations = []
        for i in range(1, len(entries)):
            if entries[i].seq_id != entries[i - 1].seq_id + 1:
                seq_violations.append(i)

        dedup_violations = []
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                if entries[j].timestamp - entries[i].timestamp > 5.0:
                    break
                if (entries[i].source_id == entries[j].source_id and
                        entries[i].payload == entries[j].payload):
                    dedup_violations.append((i, j))

        index_complete = compactor.index.get_total_count() == len(entries)

        errors = []
        if ts_violations:
            errors.append(
                f"Temporal monotonicity violated at positions: {ts_violations[:5]}"
            )
        if seq_violations:
            errors.append(
                f"Sequence monotonicity violated at positions: {seq_violations[:5]}"
            )
        if dedup_violations:
            errors.append(
                f"Duplicate entries within window: {dedup_violations[:5]}"
            )
        if not index_complete:
            errors.append(
                f"Index incomplete: {compactor.index.get_total_count()} "
                f"indexed vs {len(entries)} entries"
            )

        assert not errors, (
            f"Pipeline invariants violated:\n" +
            "\n".join(f"  - {e}" for e in errors)
        )

    def test_recovery_then_validate(
        self, segments_dir, checkpoint_dir, tmp_output_dir
    ):
        """
        Full recovery flow with validation must produce zero errors.
        """
        manager = RecoveryManager(
            segments_dir=segments_dir,
            checkpoint_dir=checkpoint_dir,
            output_dir=tmp_output_dir,
            dedup_window=5.0,
        )

        output = manager.recover_and_compact()
        errors = manager.validate_output(output)

        assert not errors, (
            f"End-to-end recovery validation failed:\n" +
            "\n".join(f"  - {e}" for e in errors)
        )

    def test_compacted_output_preserves_all_unique_data(
        self, fresh_segments_dir, tmp_checkpoint_dir, tmp_output_dir
    ):
        """
        After compaction, all unique payloads from the input must
        be present in the output. Only true duplicates should be removed.
        """
        from src.wal_reader import WALReader

        reader = WALReader(fresh_segments_dir)
        segments = reader.load_all_segments()
        input_unique = set()
        for seg in segments:
            for entry in seg.entries:
                input_unique.add((entry.source_id, entry.payload))

        compactor = IncrementalCompactor(
            segments_dir=fresh_segments_dir,
            checkpoint_dir=tmp_checkpoint_dir,
            output_dir=tmp_output_dir,
            dedup_window=5.0,
        )
        output = compactor.run_compaction()

        output_unique = set()
        for entry in output.entries:
            output_unique.add((entry.source_id, entry.payload))

        missing = input_unique - output_unique
        assert not missing, (
            f"Compaction lost unique data. Missing {len(missing)} entries: "
            + str(list(missing)[:5])
        )
