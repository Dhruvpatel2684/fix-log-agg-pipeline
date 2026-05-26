"""
Incremental Compactor - orchestrates the compaction pipeline.

The compactor:
1. Loads checkpoint (if resuming from partial compaction)
2. Reads WAL segments (starting from checkpoint position)
3. Deduplicates entries
4. Merges across segments
5. Assigns final sequence IDs
6. Builds temporal index
7. Writes checkpoint

Sequence ID assignment:
- After merging and deduplication, entries need final sequential IDs
- The compactor assigns new seq_ids starting from (last_checkpoint_seq + 1)
- Each entry gets a unique, monotonically increasing seq_id
- The final seq_id becomes the new checkpoint's last_seq_id

Recovery semantics:
- On restart, load last checkpoint
- Resume from partial_segment_id at partial_offset
- Reuse dedup window state from checkpoint
- Continue sequence numbering from checkpoint's last_seq_id
  BUT must account for any entries already emitted in the partial segment
"""
import json
from pathlib import Path
from typing import Optional, List, Tuple

from .models import (
    LogEntry, WALSegment, Checkpoint, CompactedOutput
)
from .wal_reader import WALReader
from .dedup_engine import DedupEngine
from .merger import SegmentMerger
from .temporal_index import TemporalIndex


class CompactionError(Exception):
    pass


class IncrementalCompactor:
    """Orchestrates incremental log compaction."""

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

        self.reader = WALReader(segments_dir)
        self.dedup = DedupEngine(window_size_seconds=dedup_window)
        self.merger = SegmentMerger()
        self.index = TemporalIndex()

        self._checkpoint: Optional[Checkpoint] = None
        self._next_seq_id: int = 1

    def load_checkpoint(self) -> Optional[Checkpoint]:
        """Load the latest compaction checkpoint."""
        cp_path = self.checkpoint_dir / "latest.json"
        if not cp_path.exists():
            return None

        with open(cp_path, "r") as f:
            data = json.load(f)

        self._checkpoint = Checkpoint.from_dict(data)
        self._next_seq_id = self._checkpoint.last_seq_id + 1

        # Restore dedup state
        if self._checkpoint.dedup_window_state:
            self.dedup.restore_state(self._checkpoint.dedup_window_state)

        return self._checkpoint

    def run_compaction(self) -> CompactedOutput:
        """
        Execute one round of incremental compaction.

        Returns CompactedOutput with the compacted entries.
        """
        # Load all segments
        segments = self.reader.load_all_segments()
        if not segments:
            return CompactedOutput()

        # Filter already-processed segments
        segments_to_process = self._filter_segments(segments)
        if not segments_to_process:
            return CompactedOutput()

        # Handle partial segment resume
        segments_to_process = self._handle_partial_resume(segments_to_process)

        # Merge segments into ordered stream
        merged = self.merger.merge_segments(segments_to_process)

        # Deduplicate
        deduped = self.dedup.process_entries(merged)

        # Assign final sequence IDs
        output_entries = self._assign_sequence_ids(deduped)

        # Build temporal index
        self.index.build_from_entries(output_entries)

        # Create output
        output = CompactedOutput(
            entries=output_entries,
            final_seq_id=self._next_seq_id - 1,
            entry_count=len(output_entries),
            dropped_duplicates=len(merged) - len(deduped),
            segments_consumed=[s.segment_id for s in segments_to_process],
        )

        return output

    def _filter_segments(self, segments: List[WALSegment]) -> List[WALSegment]:
        """Remove already-processed segments."""
        if not self._checkpoint:
            return segments
        processed = set(self._checkpoint.segments_processed)
        return [s for s in segments if s.segment_id not in processed]

    def _handle_partial_resume(self, segments: List[WALSegment]) -> List[WALSegment]:
        """Handle resumption from partial segment."""
        if not self._checkpoint or not self._checkpoint.partial_segment_id:
            return segments

        result = []
        for seg in segments:
            if seg.segment_id == self._checkpoint.partial_segment_id:
                offset = self._checkpoint.partial_offset
                partial_entries = seg.entries[offset:]
                if partial_entries:
                    partial_seg = WALSegment(
                        segment_id=seg.segment_id,
                        source_id=seg.source_id,
                        entries=partial_entries,
                        created_at=seg.created_at,
                        closed=seg.closed,
                    )
                    result.append(partial_seg)
            else:
                result.append(seg)

        return result

    def _assign_sequence_ids(self, entries: List[LogEntry]) -> List[LogEntry]:
        """Assign monotonically increasing sequence IDs."""
        result = []
        for entry in entries:
            new_entry = LogEntry(
                seq_id=self._next_seq_id,
                timestamp=entry.timestamp,
                source_id=entry.source_id,
                payload=entry.payload,
                checksum=entry.checksum,
            )
            result.append(new_entry)
            self._next_seq_id += 1
        return result

    def save_checkpoint(self, output: CompactedOutput) -> None:
        """Save compaction checkpoint."""
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        cp = Checkpoint(
            last_seq_id=output.final_seq_id,
            last_timestamp=output.entries[-1].timestamp if output.entries else 0.0,
            segments_processed=output.segments_consumed,
            dedup_window_state=self.dedup.get_state(),
        )

        cp_path = self.checkpoint_dir / "latest.json"
        with open(cp_path, "w") as f:
            json.dump(cp.to_dict(), f, indent=2)

    def save_output(self, output: CompactedOutput) -> Path:
        """Save compacted output."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.output_dir / "compacted.json"
        with open(out_path, "w") as f:
            json.dump(
                [e.to_dict() for e in output.entries],
                f, indent=2
            )
        return out_path
