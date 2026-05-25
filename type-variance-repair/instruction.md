# Type Variance Checker — Debugging Task

## Overview

A generic type assignability verification system processes type declarations, generic type parameters with variance annotations, and assignment records from multiple source modules. It determines whether each type assignment respects the declared variance of the generic container (covariant, contravariant, or invariant) and resolves type variable constraints within scoped contexts.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source, config, data, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **No external dependencies**: Uses Python standard library only

## Processing Stages

1. **Parsing** — Reads JSONL data files from `/app/runtime/data/` and filters records by configured source module categories. The configuration specifies which modules to include as a comma-separated list.

2. **Type Registration** — Builds a type hierarchy (inheritance tree) and registers generic type declarations with their variance annotations (covariant, contravariant, invariant).

3. **Assignment Checking** — Validates each type assignment record against variance rules. For covariant containers (e.g., Producer, Reader, Supplier), the source type argument must be a subtype of the target type argument. For contravariant containers (e.g., Consumer, Writer, Handler), the direction reverses: the target type argument must be a subtype of the source type argument. For invariant containers, exact type match is required. The recursion depth limit is configured in the `[checker.recursive]` section.

4. **Constraint Resolution** — Collects type variable bounds from constraint records. Each constraint has a scope (global or function-level) and a priority. Within a given scope, when multiple constraints exist for the same type variable, the highest-priority constraint determines the effective bound (last-write-wins semantics).

5. **Report Generation** — Produces output files sorted deterministically. When multiple records share the same timestamp, ordering is determined by source_module first, then by sequence number.

## Problem

The system is producing incorrect output across multiple dimensions:

- Some type assignments that should be flagged as violations are being marked valid, and vice versa
- One source module's records appear to be missing entirely from the output
- The constraint resolver is producing compound bounds instead of single resolved types
- Output ordering is non-deterministic when records share timestamps across different source modules

## Expected Correct Output

When functioning correctly, the system should:

- Process records from ALL four source modules (core_types, collections, io_handlers, functional)
- Correctly identify covariant violations (e.g., `Producer<Animal>` is NOT assignable to `Producer<Cat>`)
- Correctly identify contravariant violations (e.g., `Consumer<Cat>` assigned to `Consumer<Animal>` is INVALID because Animal is not a subtype of Cat)
- Correctly validate contravariant assignments (e.g., `Consumer<Animal>` assigned to `Consumer<Cat>` IS valid because Cat is a subtype of Animal)
- Resolve each constraint to its single highest-priority bound per scope
- Produce deterministic ordering using timestamp, source_module, then sequence number

## Output Schema

### `/app/runtime/output/assignments_report.json`
| Field | Type | Description |
|-------|------|-------------|
| `total_assignments` | int | Total number of assignment records checked |
| `assignments` | list | Array of assignment result objects |
| `assignments[].id` | str | Record identifier |
| `assignments[].source_module` | str | Module the record originated from |
| `assignments[].target` | str | Target type in the assignment |
| `assignments[].source` | str | Source type being assigned |
| `assignments[].context` | str | Assignment context (return_value, parameter, local_bind) |
| `assignments[].valid` | bool | Whether the assignment is type-safe |
| `assignments[].reason` | str | Explanation of the validity decision |
| `assignments[].priority` | int | Priority level of the record |
| `assignments[].timestamp` | str | ISO timestamp of the record |
| `assignments[].seq` | int | Sequence number within source module |

### `/app/runtime/output/constraints_report.json`
| Field | Type | Description |
|-------|------|-------------|
| `total_constraints` | int | Total number of resolved constraints |
| `resolutions` | list | Array of resolution result objects |
| `resolutions[].type_var` | str | Type variable name |
| `resolutions[].scope` | str | Scope where constraint applies |
| `resolutions[].resolved_bound` | str | The effective type bound (single type name) |
| `resolutions[].priority` | int | Priority of the winning constraint |
| `resolutions[].source_module` | str | Module that declared the constraint |

### `/app/runtime/output/summary.json`
| Field | Type | Description |
|-------|------|-------------|
| `total_checked` | int | Total assignments checked |
| `valid_assignments` | int | Count of valid assignments |
| `invalid_assignments` | int | Count of violations |
| `violations` | list | List of violation detail objects |
| `violations[].id` | str | Record identifier of the violating assignment |
| `violations[].target` | str | Target type |
| `violations[].source` | str | Source type |
| `violations[].reason` | str | Explanation of why it violates |
| `violations[].source_module` | str | Originating module |
| `constraint_count` | int | Number of resolved constraints |

## Key Files

| File | Purpose |
|------|---------|
| `/app/runtime/config.ini` | Configuration: source modules, depth limits, resolution strategy |
| `/app/runtime/type_parser.py` | Parses JSONL data files, applies category filtering |
| `/app/runtime/variance_checker.py` | Implements variance-aware subtype checking |
| `/app/runtime/constraint_solver.py` | Resolves type variable bounds across scopes |
| `/app/runtime/reporter.py` | Generates structured output reports |
| `/app/runtime/run_checker.py` | Entry point orchestrating all stages |
| `/app/runtime/data/core_types.jsonl` | Core type hierarchy and assignments |
| `/app/runtime/data/collections.jsonl` | Collection types and generic assignments |
| `/app/runtime/data/io_handlers.jsonl` | IO stream types and assignments |
| `/app/runtime/data/functional.jsonl` | Functional type assignments |

## Your Task

Identify and fix defects in the runtime source files under `/app/runtime/`. The system should produce correct output matching the schema and behavioral description above. All four source modules must be processed, variance checking must follow the rules described in Stage 3, constraint resolution must use last-write-wins semantics, and output ordering must be deterministic.
