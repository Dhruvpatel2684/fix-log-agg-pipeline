#!/usr/bin/env python3
"""Repair script for type-variance-repair task.

Patches all defects and re-runs the type checker to produce correct output.
"""
import os
import sys


def patch_type_parser():
    """Fix module filtering: strip whitespace from comma-separated config values."""
    path = "/app/runtime/type_parser.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'self._allowed_modules = set(raw_modules.split(","))',
        'self._allowed_modules = set(item.strip() for item in raw_modules.split(","))'
    )
    with open(path, "w") as f:
        f.write(content)


def patch_variance_checker():
    """Fix variance checking: use declaration-site variance, not use-site context.

    The buggy code determines variance direction from the assignment context
    (parameter=contravariant, return_value=covariant). Correct behavior uses
    the declared variance annotation on the generic type parameter.
    """
    path = "/app/runtime/variance_checker.py"
    with open(path, "r") as f:
        content = f.read()
    old = '''        # Determine effective variance from the usage context:
        # parameter positions are input (contravariant direction)
        # return_value positions are output (covariant direction)
        # local_bind requires exact match (invariant)
        if context == "return_value":
            effective_variance = "covariant"
        elif context == "parameter":
            effective_variance = "contravariant"
        else:
            effective_variance = "invariant"'''
    new = '''        # Use the declared variance annotation on the generic type
        # to determine the subtyping direction for the type argument
        effective_variance = variance'''
    content = content.replace(old, new)
    with open(path, "w") as f:
        f.write(content)


def patch_constraint_solver():
    """Fix constraint resolution: use greatest lower bound (most specific), not LUB.

    The buggy code selects the bound with minimum depth (most general/widest).
    Correct behavior selects maximum depth (most specific/narrowest) — the GLB.
    """
    path = "/app/runtime/constraint_solver.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        "# Find the bound with minimum depth (closest to root = most general)",
        "# Find the bound with maximum depth (furthest from root = most specific)"
    )
    content = content.replace(
        "if d < best_depth:",
        "if d > best_depth:"
    )
    with open(path, "w") as f:
        f.write(content)


def patch_run_checker():
    """Fix sort ordering: add source_module as tiebreaker for deterministic output."""
    path = "/app/runtime/run_checker.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        "key=lambda r: (r.timestamp, r.seq)",
        "key=lambda r: (r.timestamp, r.source_module, r.seq)"
    )
    with open(path, "w") as f:
        f.write(content)


def main():
    patch_type_parser()
    patch_variance_checker()
    patch_constraint_solver()
    patch_run_checker()

    # Re-run with fixed code
    sys.path.insert(0, "/app")
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]
    from runtime.run_checker import main as run_main
    run_main()


if __name__ == "__main__":
    main()
