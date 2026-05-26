"""
Repair script for the type flow analysis checker.

Fixes the function subtype checking logic to correctly implement
contravariant parameter type checking.
"""

import os

CHECKER_PATH = "/app/runtime/checker.py"


def apply_repair():
    """Apply the repair to the checker module."""
    with open(CHECKER_PATH, "r") as f:
        content = f.read()

    # The bug is in _check_function_subtype: parameter types are checked
    # with the wrong direction. The check should be contravariant (flipped).
    buggy_code = "if not self.is_subtype(param_t1, param_t2):"
    fixed_code = "if not self.is_subtype(param_t2, param_t1):"

    if buggy_code not in content:
        print("[repair] Target code not found - may already be fixed")
        return

    content = content.replace(buggy_code, fixed_code, 1)

    with open(CHECKER_PATH, "w") as f:
        f.write(content)

    print("[repair] Successfully applied fix to checker.py")
    print("[repair] Changed parameter subtype check direction (contravariant)")


if __name__ == "__main__":
    apply_repair()
