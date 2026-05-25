#!/usr/bin/env python3
"""
Apply the solution fixes to the broken pipeline code.

This script fixes 4 interacting bugs:
1. dedup_engine.py - Window boundary comparison (strict < -> <=)
2. merger.py - Sort key (seq_id only -> (timestamp, seq_id))
3. temporal_index.py - Range off-by-one (len-1 -> len)
4. compactor.py - Sequence resume after partial checkpoint
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "environment" / "src"


def fix_dedup_engine():
    """Fix: window boundary should be inclusive (<=) not exclusive (<)."""
    path = SRC / "dedup_engine.py"
    content = path.read_text()
    old = "            if window_start < ts < window_end:"
    new = "            if window_start <= ts <= window_end:"
    content = content.replace(old, new)
    path.write_text(content)
    print(f"  Fixed: {path.name}")


def fix_merger():
    """Fix: sort by (timestamp, seq_id) not just seq_id."""
    path = SRC / "merger.py"
    content = path.read_text()
    content = content.replace(
        "sorted_entries = sorted(all_entries, key=lambda e: e.seq_id)",
        "sorted_entries = sorted(all_entries, key=lambda e: (e.timestamp, e.seq_id))"
    )
    path.write_text(content)
    print(f"  Fixed: {path.name}")


def fix_temporal_index():
    """Fix: range should include last entry (len not len-1)."""
    path = SRC / "temporal_index.py"
    content = path.read_text()
    content = content.replace(
        "for i in range(0, len(entries) - 1):",
        "for i in range(len(entries)):"
    )
    path.write_text(content)
    print(f"  Fixed: {path.name}")


def fix_compactor():
    """Fix: account for already-emitted entries when resuming from checkpoint."""
    path = SRC / "compactor.py"
    content = path.read_text()
    old = "        self._next_seq_id = self._checkpoint.last_seq_id + 1"
    new = (
        "        # Account for entries emitted during partial compaction\n"
        "        base_seq = self._checkpoint.last_seq_id\n"
        "        if self._checkpoint.partial_segment_id and self._checkpoint.partial_offset > 0:\n"
        "            base_seq = self._checkpoint.last_seq_id + self._checkpoint.partial_offset\n"
        "        self._next_seq_id = base_seq + 1"
    )
    content = content.replace(old, new)
    path.write_text(content)
    print(f"  Fixed: {path.name}")


if __name__ == "__main__":
    print("Applying fixes to log aggregation pipeline...")
    fix_dedup_engine()
    fix_merger()
    fix_temporal_index()
    fix_compactor()
    print("All fixes applied successfully.")
