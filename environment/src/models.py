"""
Core data models for the log aggregation pipeline.

Entries flow through: WAL segments -> dedup -> merge -> compact -> output
"""
from dataclasses import dataclass, field
from typing import List, Optional
import json


@dataclass
class LogEntry:
    """A single log entry in the pipeline."""
    seq_id: int
    timestamp: float
    source_id: str
    payload: str
    checksum: int = 0

    def to_dict(self) -> dict:
        return {
            "seq_id": self.seq_id,
            "timestamp": self.timestamp,
            "source_id": self.source_id,
            "payload": self.payload,
            "checksum": self.checksum,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LogEntry":
        return cls(
            seq_id=d["seq_id"],
            timestamp=d["timestamp"],
            source_id=d["source_id"],
            payload=d["payload"],
            checksum=d.get("checksum", 0),
        )


@dataclass
class WALSegment:
    """A Write-Ahead Log segment containing ordered entries."""
    segment_id: str
    source_id: str
    entries: List[LogEntry] = field(default_factory=list)
    created_at: float = 0.0
    closed: bool = False

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "source_id": self.source_id,
            "entries": [e.to_dict() for e in self.entries],
            "created_at": self.created_at,
            "closed": self.closed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "WALSegment":
        return cls(
            segment_id=d["segment_id"],
            source_id=d["source_id"],
            entries=[LogEntry.from_dict(e) for e in d["entries"]],
            created_at=d.get("created_at", 0.0),
            closed=d.get("closed", False),
        )


@dataclass
class Checkpoint:
    """Compaction checkpoint - records progress of incremental compaction."""
    last_seq_id: int
    last_timestamp: float
    segments_processed: List[str]
    partial_segment_id: Optional[str] = None
    partial_offset: int = 0
    dedup_window_state: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "last_seq_id": self.last_seq_id,
            "last_timestamp": self.last_timestamp,
            "segments_processed": self.segments_processed,
            "partial_segment_id": self.partial_segment_id,
            "partial_offset": self.partial_offset,
            "dedup_window_state": self.dedup_window_state,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Checkpoint":
        return cls(
            last_seq_id=d["last_seq_id"],
            last_timestamp=d["last_timestamp"],
            segments_processed=d["segments_processed"],
            partial_segment_id=d.get("partial_segment_id"),
            partial_offset=d.get("partial_offset", 0),
            dedup_window_state=d.get("dedup_window_state", {}),
        )


@dataclass
class CompactedOutput:
    """Result of a compaction run."""
    entries: List[LogEntry] = field(default_factory=list)
    final_seq_id: int = 0
    entry_count: int = 0
    dropped_duplicates: int = 0
    segments_consumed: List[str] = field(default_factory=list)
