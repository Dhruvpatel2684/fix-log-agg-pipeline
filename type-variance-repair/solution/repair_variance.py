#!/usr/bin/env python3
"""Repair script for type-variance-repair task.

Patches all four bugs and re-runs the type checker to produce correct output.
"""
import os
import sys


def patch_type_parser():
    """Fix Bug A: whitespace in comma-split module list.
    
    The config has 'modules = core_types,collections,io_handlers, functional'
    with a space before 'functional'. The parser splits on comma without
    stripping, so ' functional' never matches 'functional'.
    """
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
    """Fix Bug B: wrong config section for recursion depth.
    
    Code reads from [checker] (max_recursion_depth = 50) instead of
    [checker.recursive] (max_recursion_depth = 5). The correct section
    is referenced in instruction.md Stage 3.
    """
    path = "/app/runtime/variance_checker.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'self._max_depth = self._config.getint("checker", "max_recursion_depth")',
        'self._max_depth = self._config.getint("checker.recursive", "max_recursion_depth")'
    )
    # Fix Bug E: contravariant check uses wrong direction
    # The buggy code checks is_subtype(source_arg, target_arg) for contravariant
    # which is the COVARIANT check. For contravariant, it should check
    # is_subtype(target_arg, source_arg) - the direction reverses.
    content = content.replace(
        '''        elif variance == "contravariant":
            # Contravariant: the relationship reverses direction
            # e.g., Consumer<Animal> assignable to Consumer<Cat> because Cat <: Animal
            # Check: source_arg is supertype of target_arg
            valid = self.is_subtype(source_arg, target_arg)''',
        '''        elif variance == "contravariant":
            # Contravariant: the relationship reverses direction
            # e.g., Consumer<Animal> assignable to Consumer<Cat> because Cat <: Animal
            # Check: target_arg must be subtype of source_arg
            valid = self.is_subtype(target_arg, source_arg)'''
    )
    with open(path, "w") as f:
        f.write(content)


def patch_constraint_solver():
    """Fix Bug C: constraint solver accumulates bounds instead of last-write-wins.
    
    The solver appends new bounds to existing ones (bound += ',new_bound')
    and sums priorities. It should replace with the new (higher priority) bound.
    """
    path = "/app/runtime/constraint_solver.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        '''            else:
                # Higher priority constraint overrides lower
                existing = self._constraints[scope][type_var]
                existing["bound"] += f",{record.bound}"
                existing["priority"] += record.priority''',
        '''            else:
                # Higher priority constraint overrides lower
                existing = self._constraints[scope][type_var]
                existing["bound"] = record.bound
                existing["priority"] = record.priority
                existing["source_module"] = record.source_module'''
    )
    with open(path, "w") as f:
        f.write(content)


def patch_run_checker():
    """Fix Bug D: sort tiebreaker missing source_module.
    
    When records share the same timestamp, the sort uses only (timestamp, seq).
    But seq is local to each stream/module, so two records from different modules
    can have the same (timestamp, seq). Need source_module as middle key.
    """
    path = "/app/runtime/run_checker.py"
    with open(path, "r") as f:
        content = f.read()
    content = content.replace(
        'key=lambda r: (r.timestamp, r.seq)',
        'key=lambda r: (r.timestamp, r.source_module, r.seq)'
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
