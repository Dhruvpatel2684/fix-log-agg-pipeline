"""
Type Flow Analysis Runtime
==========================

A gradual type system checker that validates type assignments in simplified
programming language specifications. Supports primitive types, function types,
generic container types, union types, and a configurable type hierarchy.

Modules:
    types       - Type representations and construction
    parser      - JSON program spec parsing
    checker     - Subtype relation and assignability checking
    validator   - Assignment validation with confidence scoring
    reporter    - Structured JSON output generation
    run_analysis - Entry point for batch analysis
"""

__version__ = "1.4.2"
__author__ = "Type Systems Research Group"
