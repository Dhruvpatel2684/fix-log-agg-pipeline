# Type Variance Checker — Debugging Task

## Overview

A generic type assignability verification system processes type declarations, generic type parameters with variance annotations, and assignment records from multiple source modules. It determines whether each type assignment respects the declared variance of the generic container (covariant, contravariant, or invariant) and resolves type variable constraints using lattice operations on the type hierarchy.

## System Environment

- **Language**: Python 3.11
- **Runtime**: `/app/runtime/` (source, config, data, output)
- **Global system-wide tooling**: `uv` and `pytest` are available
- **No external dependencies**: Uses Python standard library only

## Processing Stages

1. **Parsing** — Reads JSONL data files from `/app/runtime/data/` and filters records by configured source module categories. The configuration specifies which modules to include as a comma-separated list.

2. **Type Registration** — Builds a type hierarchy (inheritance tree) and registers generic type declarations with their variance annotations (covariant, contravariant, invariant).

3. **Assignment Checking** — Validates each type assignment record against declaration-site variance rules. The variance annotation declared on the generic type parameter determines the subtyping direction, regardless of the syntactic position where the assignment occurs. For covariant containers, source_arg must be a subtype of target_arg. For contravariant containers, target_arg must be a subtype of source_arg. For invariant containers, exact type match is required. The recursion depth limit is configured in the `[checker.bounds]` section.

4. **Constraint Resolution** — Collects type variable bounds from constraint records. Each constraint has a scope and a priority. Within a scope, when multiple bounds exist for the same type variable, the resolver selects the greatest lower bound (GLB) — the most specific type (deepest in the hierarchy) that is a subtype of all other bounds. This narrows the type variable to its tightest valid binding.

5. **Report Generation** — Produces output files sorted deterministically. When multiple records share the same timestamp, ordering is determined by source_module first, then by sequence number.

## Problem

The system is producing incorrect output across multiple dimensions:

- Some type assignments involving generic types in cross-position usage (e.g., a covariant container passed as a parameter, or a contravariant container used as a return value) are being checked with incorrect variance semantics
- One source module's records appear to be missing entirely from the output
- The constraint resolver is selecting overly general bounds instead of the most specific ones
- Output ordering is non-deterministic when records share timestamps across different source modules

## Expected Correct Output

When functioning correctly, the system should:

- Process records from ALL four source modules (core_types, collections, io_handlers, functional)
- Apply variance rules based on the DECLARED variance of the generic type, not the assignment context
- Resolve each constraint scope to its greatest lower bound (most specific type in the hierarchy)
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
| `resolutions[].resolved_bound` | str | The effective type bound (most specific type) |
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
| `/app/runtime/constraint_solver.py` | Resolves type variable bounds via lattice operations |
| `/app/runtime/reporter.py` | Generates structured output reports |
| `/app/runtime/run_checker.py` | Entry point orchestrating all stages |
| `/app/runtime/data/core_types.jsonl` | Core type hierarchy and assignments |
| `/app/runtime/data/collections.jsonl` | Collection types and generic assignments |
| `/app/runtime/data/io_handlers.jsonl` | IO stream types and assignments |
| `/app/runtime/data/functional.jsonl` | Functional type assignments |

## Your Task

Identify and fix defects in the runtime source files under `/app/runtime/`. The system should produce correct output matching the schema and behavioral description above. All four source modules must be processed, variance checking must use declaration-site semantics, constraint resolution must select the greatest lower bound, and output ordering must be deterministic.
