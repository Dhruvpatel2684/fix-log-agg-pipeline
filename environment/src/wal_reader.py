"""
WAL Segment Reader - reads and validates WAL segment files.

Handles:
- Loading segments from JSON fixture files
- Validating segment integrity (checksums, ordering)
- Providing iteration interface over entries
"""
import json
import zlib
from pathlib import Path
from typing import List, Iterator, Optional

from .models import WALSegment, LogEntry


class WALReaderError(Exception):
    pass


class WALReader:
    """Reads WAL segments from disk and provides validated entry streams."""

    def __init__(self, segments_dir: Path):
        self.segments_dir = segments_dir
        self._loaded_segments: List[WALSegment] = []

    def discover_segments(self) -> List[str]:
        """Find all segment files in the directory."""
        if not self.segments_dir.exists():
            return []
        files = sorted(self.segments_dir.glob("segment_*.json"))
        return [f.stem for f in files]

    def load_segment(self, segment_id: str) -> WALSegment:
        """Load and validate a single segment."""
        path = self.segments_dir / f"{segment_id}.json"
        if not path.exists():
            raise WALReaderError(f"Segment file not found: {path}")

        with open(path, "r") as f:
            data = json.load(f)

        segment = WALSegment.from_dict(data)
        self._validate_segment(segment)
        return segment

    def load_all_segments(self) -> List[WALSegment]:
        """Load all discovered segments."""
        segment_ids = self.discover_segments()
        segments = []
        for sid in segment_ids:
            seg = self.load_segment(sid)
            segments.append(seg)
        self._loaded_segments = segments
        return segments

    def iter_entries(self, segment: WALSegment, offset: int = 0) -> Iterator[LogEntry]:
        """Iterate entries from a segment starting at offset."""
        for i in range(offset, len(segment.entries)):
            yield segment.entries[i]

    def _validate_segment(self, segment: WALSegment) -> None:
        """Validate segment integrity."""
        for entry in segment.entries:
            if entry.checksum != 0:
                expected = zlib.crc32(entry.payload.encode()) & 0xFFFFFFFF
                if entry.checksum != expected:
                    raise WALReaderError(
                        f"Checksum mismatch for entry {entry.seq_id} "
                        f"in segment {segment.segment_id}"
                    )

    def get_segment_time_range(self, segment: WALSegment) -> tuple:
        """Get (min_ts, max_ts) for a segment."""
        if not segment.entries:
            return (0.0, 0.0)
        timestamps = [e.timestamp for e in segment.entries]
        return (min(timestamps), max(timestamps))
