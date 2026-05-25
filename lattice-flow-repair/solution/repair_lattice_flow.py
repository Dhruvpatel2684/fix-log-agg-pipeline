#!/usr/bin/env python3
"""Repair script for the product lattice information flow analysis system.

Patches identified defects in the runtime source code and re-runs
the analysis to produce correct output.
"""

import sys


def patch_lattice():
    """Fix product lattice operations: dominance, join, and distance."""
    path = "/app/runtime/lattice.py"
    with open(path, "r") as f:
        content = f.read()

    # Fix Bug 1: dominates() uses sum-based comparison instead of componentwise
    # The product lattice partial order requires BOTH components to be >=
    old_dominates = '''        # Product lattice ordering: compare using combined rank precedence
        # Higher combined classification indicates stronger dominance
        if (to_c + to_i) > (from_c + from_i):
            return True
        if (to_c + to_i) == (from_c + from_i):
            return to_c > from_c
        return False'''
    new_dominates = '''        # Product lattice ordering: componentwise comparison
        # Both dimensions must be non-decreasing, at least one strict
        return to_c >= from_c and to_i >= from_i and (to_c > from_c or to_i > from_i)'''
    content = content.replace(old_dominates, new_dominates)

    # Fix Bug 2: join() uses averaged midpoint instead of componentwise max
    old_join = '''        # Compute join: find the least element dominating both
        # Use the combined rank to determine the effective upper bound
        combined_c = (c_a + c_b + 1) // 2 if c_a != c_b else c_a
        combined_i = (i_a + i_b + 1) // 2 if i_a != i_b else i_a

        # Ensure we don't exceed lattice bounds
        combined_c = min(combined_c, len(self._conf_levels) - 1)
        combined_i = min(combined_i, len(self._integ_levels) - 1)'''
    new_join = '''        # Compute join: componentwise maximum (least upper bound)
        combined_c = max(c_a, c_b)
        combined_i = max(i_a, i_b)'''
    content = content.replace(old_join, new_join)

    # Fix Bug 3: flow_distance() uses Manhattan (L1) instead of Chebyshev (L-inf)
    old_distance = '''        # Total displacement across both lattice dimensions
        return abs(to_c - from_c) + abs(to_i - from_i)'''
    new_distance = '''        # Maximum displacement across lattice dimensions (L-infinity)
        return max(abs(to_c - from_c), abs(to_i - from_i))'''
    content = content.replace(old_distance, new_distance)

    with open(path, "w") as f:
        f.write(content)


def patch_loader():
    """Fix deduplication to include source_id in the identity key."""
    path = "/app/runtime/loader.py"
    with open(path, "r") as f:
        content = f.read()

    # Fix Bug 4: dedup key uses (entity, bucket) instead of (entity, source_id, bucket)
    old_dedup = '''        # Deduplication key: entity within a time bucket
        ts = datetime.fromisoformat(event["timestamp"])
        bucket = int(ts.timestamp()) // window_seconds
        dedup_key = (event["entity"], str(bucket))'''
    new_dedup = '''        # Deduplication key: entity + source within a time bucket
        ts = datetime.fromisoformat(event["timestamp"])
        bucket = int(ts.timestamp()) // window_seconds
        dedup_key = (event["entity"], event["source_id"], str(bucket))'''
    content = content.replace(old_dedup, new_dedup)

    with open(path, "w") as f:
        f.write(content)


def main():
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
