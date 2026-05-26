# Type Flow Analysis - Debugging Task

## Overview

You are debugging a **type flow analysis system** that validates type assignments in simplified programming language specifications. The system checks whether values of one type can be safely assigned to variables of another type based on subtype relationships.

The analysis system is currently producing incorrect validation results for certain assignments. Your task is to identify and fix the issue.

Global system-wide tooling: `uv` and `pytest` are available.

## System Architecture

The system consists of 6 modules located at `/app/runtime/`:

| Module | Path | Description |
|--------|------|-------------|
| types | `/app/runtime/types.py` | Type representations (PrimitiveType, FunctionType, GenericType, UnionType, TopType, BottomType) |
| parser | `/app/runtime/parser.py` | Parses JSON program specs into typed AST representations |
| checker | `/app/runtime/checker.py` | Implements the subtype relation and assignability checking |
| validator | `/app/runtime/validator.py` | Validates assignment statements using the subtype checker |
| reporter | `/app/runtime/reporter.py` | Generates structured JSON output reports |
| run_analysis | `/app/runtime/run_analysis.py` | Entry point for batch analysis |

## Type System

The system implements a type hierarchy:

```
object (top type - supertype of everything)
├── number
│   ├── int
│   └── float
├── string
├── bool
├── Animal
│   ├── Dog
│   └── Cat
└── Vehicle
    ├── Car
    └── Truck
```

### Supported Type Forms

1. **Primitive Types**: `int`, `float`, `string`, `bool`, `void`, named entity types
2. **Function Types**: `(ParamType1, ParamType2, ...) -> ReturnType`
3. **Generic Container Types**: `List[T]`, `Map[K, V]`, `Set[T]`
4. **Union Types**: `T1 | T2 | ... | Tn`
5. **Top Type**: `object` (universal supertype)
6. **Bottom Type**: `never` (universal subtype)

### Assignment Validity Rules

An assignment `x: TargetType = value: SourceType` is **valid** if and only if `SourceType` is a subtype of `TargetType`. The subtype rules are:

- **Reflexivity**: Every type is a subtype of itself
- **Transitivity**: If A <: B and B <: C, then A <: C
- **Top**: Every type is a subtype of `object`
- **Bottom**: `never` is a subtype of every type
- **Primitives**: Follow the declared hierarchy (e.g., `Dog <: Animal <: object`)
- **Generics**: `Container[A] <: Container[B]` if `A <: B` (same base required)
- **Unions**: `T <: U1 | U2` if `T <: U1` or `T <: U2`; `U1 | U2 <: T` if both `U1 <: T` and `U2 <: T`
- **Functions**: A function type `(A) -> R1` is a subtype of `(B) -> R2` when the function can safely substitute — parameter types must be compatible for type-safe substitution, and `R1 <: R2`

## Input Data

Program specifications are JSON files at `/app/runtime/data/`:

| File | Description |
|------|-------------|
| `/app/runtime/data/program_alpha.json` | Basic function type and primitive assignments |
| `/app/runtime/data/program_beta.json` | Generic containers and function types with vehicle hierarchy |
| `/app/runtime/data/program_gamma.json` | Complex nested and higher-order function types |
| `/app/runtime/data/program_delta.json` | Mixed assignments with unions, generics, and functions |

Each program spec contains an array of assignments with `target_type` and `source_type` fields that the checker validates.

## Output Schema

Running the analysis produces reports at `/app/runtime/data/`:

### Main Report (`analysis_report.json`)

| Field | Type | Description |
|-------|------|-------------|
| `analysis_version` | string | Version of the analysis system |
| `generated_at` | string | ISO timestamp of generation |
| `programs` | array | Per-program validation results |
| `summary` | object | Overall statistics |
| `metadata` | object | Analysis configuration metadata |

### Per-Program Report (`report_<name>.json`)

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Program specification name |
| `total_assignments` | int | Number of assignments checked |
| `valid_count` | int | Number of valid assignments |
| `invalid_count` | int | Number of invalid assignments |
| `validity_ratio` | float | Ratio of valid to total |
| `assignments` | array | Individual assignment results |

### Assignment Result

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique assignment identifier |
| `target` | string | Target variable name |
| `target_type` | string | Display string of target type |
| `source` | string | Source expression |
| `source_type` | string | Display string of source type |
| `valid` | boolean | Whether assignment is valid |
| `confidence` | float | Confidence score (0.0-1.0) |
| `category` | string | Assignment complexity category |
| `explanation` | string | Human-readable explanation |

## Running the Analysis

```bash
cd /app
python3 -m runtime.run_analysis
```

This reads all `program_*.json` files from `/app/runtime/data/`, validates each assignment, and writes reports to the same directory.

## Running Tests

```bash
cd /app
uv run --with pytest pytest /tests/test_lattice_flow.py -v
```

## Problem Statement

The type checking system has a defect that causes it to incorrectly determine the validity of certain assignments involving function types. Some assignments that should be valid are reported as invalid, and some that should be invalid are reported as valid.

Your task is to find and fix this defect so that all test cases pass. The fix should be minimal — changing the logic rather than rewriting the system.

## Constraints

- Do not modify the test file
- Do not modify the program specification JSON files
- Do not change the type hierarchy
- The fix should be in the runtime source code
- The fix should preserve correct behavior for all other type forms (primitives, generics, unions)
