"""
Type Declaration and Program Spec Parser
=========================================

Parses JSON program specifications into typed AST representations.
Each program spec defines:
    - A set of named type declarations (aliases, custom types)
    - A set of variable declarations with type annotations
    - A set of assignment statements to validate

The parser handles:
    - Nested function types with arbitrary depth
    - Generic type instantiation with multiple type arguments
    - Union type parsing and normalization
    - Type alias resolution during parsing
    - Contextual error reporting for malformed specs
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .types import (
    BottomType,
    FunctionType,
    GenericType,
    PrimitiveType,
    TopType,
    TypeFactory,
    TypeNode,
    UnionType,
)


# ============================================================================
# Parsed Program Structures
# ============================================================================

@dataclass
class TypeDeclaration:
    """A named type declaration in a program spec."""

    name: str
    resolved_type: TypeNode
    source_line: int = 0
    doc_comment: str = ""
    is_exported: bool = True


@dataclass
class VariableDeclaration:
    """A variable declaration with a type annotation."""

    name: str
    declared_type: TypeNode
    is_mutable: bool = True
    scope: str = "module"
    initialization_expression: str = ""


@dataclass
class AssignmentStatement:
    """An assignment statement to validate."""

    target_variable: str
    target_type: TypeNode
    source_expression: str
    source_type: TypeNode
    line_number: int = 0
    context: str = ""
    expected_valid: Optional[bool] = None


@dataclass
class ProgramSpec:
    """A complete parsed program specification."""

    name: str
    version: str
    type_declarations: List[TypeDeclaration] = field(default_factory=list)
    variable_declarations: List[VariableDeclaration] = field(default_factory=list)
    assignments: List[AssignmentStatement] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    parse_warnings: List[str] = field(default_factory=list)


# ============================================================================
# Type Parsing Engine
# ============================================================================

class TypeParser:
    """
    Parses type expressions from string or structured representations.
    Maintains a registry of known type aliases for resolution.
    """

    PRIMITIVE_NAMES = frozenset({
        "int", "float", "string", "bool", "void", "number",
        "object", "never", "any",
    })

    ENTITY_NAMES = frozenset({
        "Animal", "Dog", "Cat",
        "Vehicle", "Car", "Truck",
    })

    GENERIC_BASES = frozenset({"List", "Map", "Set", "Optional", "Pair"})

    def __init__(self) -> None:
        self._aliases: Dict[str, TypeNode] = {}
        self._parse_depth: int = 0
        self._max_depth: int = 32
        self._warnings: List[str] = []

    def register_alias(self, name: str, target: TypeNode) -> None:
        """Register a type alias for resolution during parsing."""
        self._aliases[name] = target

    def clear_aliases(self) -> None:
        """Clear all registered type aliases."""
        self._aliases.clear()

    def get_warnings(self) -> List[str]:
        """Retrieve accumulated parse warnings."""
        return list(self._warnings)

    def parse_type_expression(self, expr: Any) -> TypeNode:
        """
        Parse a type expression into a TypeNode.

        Accepts:
            - String: "int", "(int) -> string", "List[int]", "int | string"
            - Dict: {"kind": "function", "params": [...], "return": {...}}
        """
        self._parse_depth += 1
        if self._parse_depth > self._max_depth:
            self._warnings.append(f"Maximum parse depth exceeded at: {expr}")
            self._parse_depth -= 1
            return TopType()

        try:
            if isinstance(expr, str):
                return self._parse_string_type(expr)
            elif isinstance(expr, dict):
                return self._parse_dict_type(expr)
            else:
                self._warnings.append(f"Unexpected type expression format: {type(expr)}")
                return TopType()
        finally:
            self._parse_depth -= 1

    def _parse_string_type(self, s: str) -> TypeNode:
        """Parse a string type expression."""
        s = s.strip()

        if not s:
            return TopType()

        # Check for union types (split on |)
        if "|" in s and not self._is_inside_parens(s, s.index("|")):
            parts = self._split_union(s)
            if len(parts) > 1:
                members = [self.parse_type_expression(p.strip()) for p in parts]
                return TypeFactory.union(*members)

        # Check for function types: (...) -> ...
        if s.startswith("(") and "->" in s:
            arrow_pos = self._find_arrow(s)
            if arrow_pos > 0:
                params_str = s[1:self._find_matching_paren(s, 0)]
                return_str = s[arrow_pos + 2:].strip()
                params = self._parse_param_list(params_str)
                ret = self.parse_type_expression(return_str)
                return FunctionType(param_types=tuple(params), return_type=ret)

        # Check for generic types: Name[...]
        bracket_pos = s.find("[")
        if bracket_pos > 0 and s.endswith("]"):
            base = s[:bracket_pos].strip()
            args_str = s[bracket_pos + 1:-1]
            args = self._parse_type_arg_list(args_str)
            return GenericType(base_name=base, type_args=tuple(args))

        # Check aliases
        if s in self._aliases:
            return self._aliases[s]

        # Check special types
        if s == "object":
            return TopType()
        if s == "never":
            return BottomType()

        # Default to primitive/named type
        if s in self.PRIMITIVE_NAMES or s in self.ENTITY_NAMES:
            category = "primitive" if s in self.PRIMITIVE_NAMES else "entity"
            return PrimitiveType(name=s, category=category)

        # Unknown type - treat as named type with warning
        self._warnings.append(f"Unknown type name: '{s}', treating as named type")
        return PrimitiveType(name=s, category="unknown")

    def _parse_dict_type(self, d: Dict[str, Any]) -> TypeNode:
        """Parse a dictionary type expression."""
        kind = d.get("kind", d.get("type", ""))

        if kind == "primitive" or kind == "named":
            name = d.get("name", "object")
            category = d.get("category", "primitive")
            return PrimitiveType(name=name, category=category)

        elif kind == "function":
            params_raw = d.get("params", d.get("parameters", []))
            params = [self.parse_type_expression(p) for p in params_raw]
            ret_raw = d.get("return", d.get("returnType", {"kind": "primitive", "name": "void"}))
            ret = self.parse_type_expression(ret_raw)
            label = d.get("label", "")
            return FunctionType(
                param_types=tuple(params),
                return_type=ret,
                label=label,
            )

        elif kind == "generic":
            base = d.get("base", d.get("name", "List"))
            args_raw = d.get("args", d.get("typeArgs", []))
            args = [self.parse_type_expression(a) for a in args_raw]
            return GenericType(base_name=base, type_args=tuple(args))

        elif kind == "union":
            members_raw = d.get("members", d.get("types", []))
            members = [self.parse_type_expression(m) for m in members_raw]
            return TypeFactory.union(*members)

        elif kind == "top" or kind == "object":
            return TopType()

        elif kind == "bottom" or kind == "never":
            return BottomType()

        else:
            self._warnings.append(f"Unknown type dict kind: '{kind}'")
            return TopType()

    def _parse_param_list(self, s: str) -> List[TypeNode]:
        """Parse a comma-separated parameter type list."""
        if not s.strip():
            return []
        parts = self._split_at_commas(s)
        return [self.parse_type_expression(p.strip()) for p in parts]

    def _parse_type_arg_list(self, s: str) -> List[TypeNode]:
        """Parse a comma-separated type argument list."""
        if not s.strip():
            return []
        parts = self._split_at_commas(s)
        return [self.parse_type_expression(p.strip()) for p in parts]

    def _split_at_commas(self, s: str) -> List[str]:
        """Split string at top-level commas (respecting brackets/parens)."""
        parts: List[str] = []
        current = ""
        depth = 0
        for ch in s:
            if ch in "([":
                depth += 1
                current += ch
            elif ch in ")]":
                depth -= 1
                current += ch
            elif ch == "," and depth == 0:
                parts.append(current)
                current = ""
            else:
                current += ch
        if current:
            parts.append(current)
        return parts

    def _split_union(self, s: str) -> List[str]:
        """Split a string at top-level | characters."""
        parts: List[str] = []
        current = ""
        depth = 0
        for ch in s:
            if ch in "([":
                depth += 1
                current += ch
            elif ch in ")]":
                depth -= 1
                current += ch
            elif ch == "|" and depth == 0:
                parts.append(current)
                current = ""
            else:
                current += ch
        if current:
            parts.append(current)
        return parts

    def _is_inside_parens(self, s: str, pos: int) -> bool:
        """Check if position is inside parentheses."""
        depth = 0
        for i in range(pos):
            if s[i] in "([":
                depth += 1
            elif s[i] in ")]":
                depth -= 1
        return depth > 0

    def _find_arrow(self, s: str) -> int:
        """Find the position of -> at the correct nesting level."""
        depth = 0
        i = 0
        while i < len(s) - 1:
            if s[i] in "([":
                depth += 1
            elif s[i] in ")]":
                depth -= 1
            elif s[i] == "-" and s[i + 1] == ">" and depth == 0:
                return i
            i += 1
        return -1

    def _find_matching_paren(self, s: str, start: int) -> int:
        """Find the matching closing parenthesis."""
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "(":
                depth += 1
            elif s[i] == ")":
                depth -= 1
                if depth == 0:
                    return i
        return len(s) - 1


# ============================================================================
# Program Spec Parser
# ============================================================================

class ProgramSpecParser:
    """
    Parses complete program specifications from JSON files.
    """

    def __init__(self) -> None:
        self._type_parser = TypeParser()
        self._parsed_count: int = 0
        self._error_count: int = 0

    def parse_file(self, filepath: str) -> ProgramSpec:
        """Parse a program spec from a JSON file."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Program spec not found: {filepath}")

        with open(path, "r") as f:
            data = json.load(f)

        return self._parse_spec_data(data, path.stem)

    def parse_multiple(self, filepaths: Sequence[str]) -> List[ProgramSpec]:
        """Parse multiple program spec files."""
        specs: List[ProgramSpec] = []
        for fp in filepaths:
            try:
                spec = self.parse_file(fp)
                specs.append(spec)
                self._parsed_count += 1
            except Exception as e:
                self._error_count += 1
                specs.append(ProgramSpec(
                    name=Path(fp).stem,
                    version="0.0.0",
                    parse_warnings=[f"Parse error: {e}"],
                ))
        return specs

    def get_stats(self) -> Dict[str, int]:
        """Return parsing statistics."""
        return {
            "parsed": self._parsed_count,
            "errors": self._error_count,
        }

    def _parse_spec_data(self, data: Dict[str, Any], default_name: str) -> ProgramSpec:
        """Parse a program spec from loaded JSON data."""
        self._type_parser.clear_aliases()

        name = data.get("name", default_name)
        version = data.get("version", "1.0.0")
        metadata = data.get("metadata", {})

        # Parse type declarations first (for alias resolution)
        type_decls = self._parse_type_declarations(data.get("types", {}))

        # Parse variable declarations
        var_decls = self._parse_variable_declarations(data.get("variables", {}))

        # Parse assignments
        assignments = self._parse_assignments(data.get("assignments", []))

        warnings = self._type_parser.get_warnings()

        return ProgramSpec(
            name=name,
            version=version,
            type_declarations=type_decls,
            variable_declarations=var_decls,
            assignments=assignments,
            metadata=metadata,
            parse_warnings=warnings,
        )

    def _parse_type_declarations(self, types_data: Dict[str, Any]) -> List[TypeDeclaration]:
        """Parse type declarations and register aliases."""
        declarations: List[TypeDeclaration] = []

        for name, type_expr in types_data.items():
            resolved = self._type_parser.parse_type_expression(type_expr)
            self._type_parser.register_alias(name, resolved)
            declarations.append(TypeDeclaration(
                name=name,
                resolved_type=resolved,
                doc_comment=f"Type alias for {resolved.display()}",
            ))

        return declarations

    def _parse_variable_declarations(self, vars_data: Dict[str, Any]) -> List[VariableDeclaration]:
        """Parse variable declarations."""
        declarations: List[VariableDeclaration] = []

        for name, var_info in vars_data.items():
            if isinstance(var_info, (str, dict)):
                declared_type = self._type_parser.parse_type_expression(var_info)
                declarations.append(VariableDeclaration(
                    name=name,
                    declared_type=declared_type,
                ))
            elif isinstance(var_info, dict) and "type" in var_info:
                declared_type = self._type_parser.parse_type_expression(var_info["type"])
                declarations.append(VariableDeclaration(
                    name=name,
                    declared_type=declared_type,
                    is_mutable=var_info.get("mutable", True),
                    scope=var_info.get("scope", "module"),
                ))

        return declarations

    def _parse_assignments(self, assignments_data: List[Dict[str, Any]]) -> List[AssignmentStatement]:
        """Parse assignment statements."""
        statements: List[AssignmentStatement] = []

        for idx, assign_data in enumerate(assignments_data):
            target_var = assign_data.get("target", assign_data.get("variable", f"var_{idx}"))
            target_type_expr = assign_data.get("target_type", assign_data.get("declared_type"))
            source_expr = assign_data.get("source", assign_data.get("expression", ""))
            source_type_expr = assign_data.get("source_type", assign_data.get("value_type"))

            if target_type_expr is None or source_type_expr is None:
                continue

            target_type = self._type_parser.parse_type_expression(target_type_expr)
            source_type = self._type_parser.parse_type_expression(source_type_expr)

            expected = assign_data.get("expected_valid", None)

            statements.append(AssignmentStatement(
                target_variable=target_var,
                target_type=target_type,
                source_expression=source_expr,
                source_type=source_type,
                line_number=assign_data.get("line", idx + 1),
                context=assign_data.get("context", ""),
                expected_valid=expected,
            ))

        return statements
