"""
Tests for crash recovery and checkpoint resumption.

When the compactor resumes from a checkpoint after partial compaction,
it must:
1. Continue sequence numbering correctly (no duplicates, no gaps)
2. Only process unprocessed entries
3. Maintain all ordering invariants
"""
import sys
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "environment"))

from src.models import LogEntry, WALSegment, Checkpoint
from src.compactor import IncrementalCompactor
from src.recovery import RecoveryManager


class TestCheckpointRecovery:
    def test_sequence_ids_are_monotonically_increasing(
        self, segments_dir, checkpoint_dir, tmp_output_dir
    ):
        """
        After recovering from checkpoint, all emitted sequence IDs
        must be strictly monotonically increasing with no gaps.
        """
        compactor = IncrementalCompactor(
            segments_dir=segments_dir,
            checkpoint_dir=checkpoint_dir,
            output_dir=tmp_output_dir,
            dedup_window=5.0,
        )
        compactor.load_checkpoint()
        output = compactor.run_compaction()

        assert len(output.entries) > 0, "Recovery produced no entries"

        for i in range(1, len(output.entries)):
            assert output.entries[i].seq_id == output.entries[i - 1].seq_id + 1, (
                f"Sequence ID gap/duplicate at position {i}: "
                f"seq_id={output.entries[i].seq_id}, "
                f"prev={output.entries[i-1].seq_id}"
            )

    def test_no_duplicate_sequence_ids_after_recovery(
        self, segments_dir, checkpoint_dir, tmp_output_dir
    ):
        """Sequence IDs in recovery output must be unique."""
        compactor = IncrementalCompactor(
            segments_dir=segments_dir,
            checkpoint_dir=checkpoint_dir,
            output_dir=tmp_output_dir,
            dedup_window=5.0,
        )
        compactor.load_checkpoint()
        output = compactor.run_compaction()

        seq_ids = [e.seq_id for e in output.entries]
        assert len(seq_ids) == len(set(seq_ids)), (
            f"Duplicate sequence IDs found: "
            f"{[s for s in seq_ids if seq_ids.count(s) > 1]}"
        )

    def test_recovery_sequence_starts_above_all_emitted(
        self, segments_dir, checkpoint_dir, tmp_output_dir
    ):
        """
        Sequence IDs after recovery must start above ALL previously
        emitted entries - not just the checkpoint's last_seq_id.

        When partial compaction occurs, entries between checkpoint.last_seq_id
        and the actual crash point were already emitted. The partial_offset
        field records how many entries from the partial segment were processed.
        New seq_ids must start above (last_seq_id + partial_offset).
        """
        cp_path = checkpoint_dir / "latest.json"
        with open(cp_path) as f:
            cp_data = json.load(f)
        checkpoint_last_seq = cp_data["last_seq_id"]
        partial_offset = cp_data.get("partial_offset", 0)

        true_last_emitted = checkpoint_last_seq + partial_offset

        compactor = IncrementalCompactor(
            segments_dir=segments_dir,
            checkpoint_dir=checkpoint_dir,
            output_dir=tmp_output_dir,
            dedup_window=5.0,
        )
        compactor.load_checkpoint()
        output = compactor.run_compaction()

        assert len(output.entries) > 0

        first_seq = output.entries[0].seq_id
        assert first_seq > true_last_emitted, (
            f"First seq_id after recovery ({first_seq}) is not above "
            f"the true last emitted seq ({true_last_emitted} = "
            f"checkpoint.last_seq_id({checkpoint_last_seq}) + "
            f"partial_offset({partial_offset})). "
            f"This would cause seq_id conflicts with pre-crash entries."
        )

    def test_recovery_manager_full_flow(
        self, segments_dir, checkpoint_dir, tmp_output_dir
    ):
        """
        The full recovery manager flow must produce valid output:
        - Monotonic timestamps
        - Monotonic sequence IDs
        - No validation errors
        """
        manager = RecoveryManager(
            segments_dir=segments_dir,
            checkpoint_dir=checkpoint_dir,
            output_dir=tmp_output_dir,
            dedup_window=5.0,
        )

        output = manager.recover_and_compact()
        assert len(output.entries) > 0

        errors = manager.validate_output(output)
        assert not errors, (
            f"Recovery output validation failed with {len(errors)} errors:\n"
            + "\n".join(errors)
        )
