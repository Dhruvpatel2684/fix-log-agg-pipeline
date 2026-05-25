#!/usr/bin/env python3
"""Repair script for abstract interval analysis system."""

import sys


def patch_domain():
    """Fix the merge operation in the domain module."""
    path = "/app/runtime/domain.py"
    with open(path, "r") as f:
        content = f.read()

    # The merge logic computes the intersection (tightest consistent interval)
    # but for sound over-approximation at branch merges, it must compute
    # the union (widest interval covering both paths).
    content = content.replace(
        "        # Combine: tightest interval consistent with all predecessors\n"
        "        new_lo = max(result.lo, state.lo)\n"
        "        new_hi = min(result.hi, state.hi)\n"
        "        if new_lo > new_hi:\n"
        "            result = Interval.bottom()\n"
        "        else:\n"
        "            result = Interval(new_lo, new_hi)",
        "        # Combine: widest interval covering all predecessors\n"
        "        new_lo = min(result.lo, state.lo)\n"
        "        new_hi = max(result.hi, state.hi)\n"
        "        result = Interval(new_lo, new_hi)"
    )

    with open(path, "w") as f:
        f.write(content)


def main():
    patch_domain()

    # Re-run analysis with fixed code
    sys.path.insert(0, "/app")
    for key in list(sys.modules.keys()):
        if key.startswith("runtime"):
            del sys.modules[key]

    from runtime.run_analysis import main as run_main
    run_main()


if __name__ == "__main__":
    main()
