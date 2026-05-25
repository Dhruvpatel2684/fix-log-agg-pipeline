#!/usr/bin/env python3
"""Repair script for lattice-based information flow analysis system.

Patches identified defects in the runtime source code and re-runs
the analysis to produce correct output.
"""

import os
import sys


def patch_analyzer():
    """Fix department filtering and configuration section reference."""
    path = "/app/runtime/analyzer.py"
    with open(path, "r") as f:
        content = f.read()

    # Fix Bug A: strip whitespace from department names in comma-split
    content = content.replace(
        'self._monitored = set(raw_depts.split(","))',
        'self._monitored = set(item.strip() for item in raw_depts.split(","))'
    )

    # Fix Bug B: read from strict analysis section
    content = content.replace(
        'self._violation_threshold = self._config.getint(\n            "analysis", "violation_threshold"\n        )',
        'self._violation_threshold = self._config.getint(\n            "analysis.strict", "violation_threshold"\n        )'
    )
    content = content.replace(
        'self._batch_window = self._config.getint(\n            "analysis", "batch_window_seconds"\n        )',
        'self._batch_window = self._config.getint(\n            "analysis.strict", "batch_window_seconds"\n        )'
    )

    # Fix Bug C: window volumes should use last-write-wins, not accumulate
    content = content.replace(
        'window_volumes[entity] = window_volumes.get(entity, 0) + vol',
        'window_volumes[entity] = vol'
    )

    with open(path, "w") as f:
        f.write(content)


def patch_lattice():
    """Fix the combined_label computation to use JOIN (max) not MEET (min)."""
    path = "/app/runtime/lattice.py"
    with open(path, "r") as f:
        content = f.read()

    # Fix Bug D (part 1): combined_label uses min (MEET) but should use max (JOIN)
    content = content.replace(
        'combined_rank = min(rank_a, rank_b)',
        'combined_rank = max(rank_a, rank_b)'
    )

    with open(path, "w") as f:
        f.write(content)


def patch_loader():
    """Fix sort key to include source_id for deterministic ordering."""
    path = "/app/runtime/loader.py"
    with open(path, "r") as f:
        content = f.read()

    # Fix Bug D (part 2): add source_id to sort key for deterministic tiebreaking
    content = content.replace(
        'all_events.sort(key=lambda e: (e["timestamp"], e["seq"]))',
        'all_events.sort(key=lambda e: (e["timestamp"], e["source_id"], e["seq"]))'
    )

    with open(path, "w") as f:
        f.write(content)


def main():
    patch_analyzer()
    patch_lattice()
    patch_loader()

    # Re-run with fixed code
    sys.path.insert(0, "/app")
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]

    from runtime.run_analysis import main as run_main
    run_main()


if __name__ == "__main__":
    main()
