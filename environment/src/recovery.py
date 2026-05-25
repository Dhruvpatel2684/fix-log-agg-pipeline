"""
Recovery Manager - coordinates crash recovery and resumption.

Handles:
- Loading last good checkpoint
- Determining which segments need reprocessing
- Coordinating with compactor for partial segment resume
- Validating recovered state consistency
"""
import json
from pathlib import Path
from typing import Optional, Tuple, List

from .models import Checkpoint, WALSegment, LogEntry, CompactedOutput
from .compactor import IncrementalCompactor


class RecoveryError(Exception):
    pass


class RecoveryManager:
    """Manages crash recovery for the compaction pipeline."""

    def __init__(
        self,
        segments_dir: Path,
        checkpoint_dir: Path,
        output_dir: Path,
        dedup_window: float = 5.0,
    ):
        self.segments_dir = segments_dir
        self.checkpoint_dir = checkpoint_dir
        self.output_dir = output_dir
        self.dedup_window = dedup_window

    def recover_and_compact(self) -> CompactedOutput:
        """
        Full recovery + compaction flow.

        1. Load checkpoint (if any)
        2. Create compactor with recovered state
        3. Run compaction
        4. Save results
        """
        compactor = IncrementalCompactor(
            segments_dir=self.segments_dir,
            checkpoint_dir=self.checkpoint_dir,
            output_dir=self.output_dir,
            dedup_window=self.dedup_window,
        )

        # Load checkpoint for resumption
        checkpoint = compactor.load_checkpoint()

        # Run compaction
        output = compactor.run_compaction()

        if output.entries:
            compactor.save_checkpoint(output)
            compactor.save_output(output)

        return output

    def get_recovery_status(self) -> dict:
        """Get current recovery status info."""
        cp_path = self.checkpoint_dir / "latest.json"
        if not cp_path.exists():
            return {"has_checkpoint": False, "status": "fresh_start"}

        with open(cp_path, "r") as f:
            data = json.load(f)

        cp = Checkpoint.from_dict(data)
        return {
            "has_checkpoint": True,
            "last_seq_id": cp.last_seq_id,
            "last_timestamp": cp.last_timestamp,
            "segments_processed": cp.segments_processed,
            "partial_segment": cp.partial_segment_id,
            "partial_offset": cp.partial_offset,
            "status": "partial_resume" if cp.partial_segment_id else "clean_resume",
        }

    def validate_output(self, output: CompactedOutput) -> List[str]:
        """
        Validate compaction output for consistency.

        Checks:
        - Monotonic sequence IDs
        - Monotonic timestamps
        - No duplicate seq_ids
        """
        errors = []

        if not output.entries:
            return errors

        seen_seqs = set()
        for i, entry in enumerate(output.entries):
            if entry.seq_id in seen_seqs:
                errors.append(
                    f"Duplicate seq_id {entry.seq_id} at position {i}"
                )
            seen_seqs.add(entry.seq_id)

            if i > 0:
                if entry.seq_id <= output.entries[i - 1].seq_id:
                    errors.append(
                        f"Non-monotonic seq_id at position {i}: "
                        f"{entry.seq_id} <= {output.entries[i-1].seq_id}"
                    )

        for i in range(1, len(output.entries)):
            if output.entries[i].timestamp < output.entries[i - 1].timestamp:
                errors.append(
                    f"Non-monotonic timestamp at position {i}: "
                    f"{output.entries[i].timestamp} < "
                    f"{output.entries[i-1].timestamp}"
                )

        return errors
