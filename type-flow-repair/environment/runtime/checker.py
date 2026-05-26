"""
Subtype Relation and Assignability Checker
==========================================

Implements the core subtype checking algorithm for the gradual type system.
The checker determines whether one type can be safely assigned to another
based on the type hierarchy and structural compatibility rules.

Key Concepts:
    - Primitive subtyping follows the declared type hierarchy
    - Generic types are checked covariantly on their type arguments
    - Union types: T1 | T2 <: T3 iff T1 <: T3 AND T2 <: T3
    - Function types: checked for compatibility of parameters and returns
    - Top type (object) is a supertype of everything
    - Bottom type (never) is a subtype of everything

The checker supports recursive types with cycle detection and provides
detailed explanations for subtype failures.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

from .types import (
    BottomType,
    FunctionType,
    GenericType,
    PrimitiveType,
    TopType,
    TypeNode,
    UnionType,
    flatten_union,
    type_complexity,
)


# ============================================================================
# Type Hierarchy Configuration
# ============================================================================

@dataclass
class TypeHierarchy:
    """
    Defines the subtype relationships between primitive/named types.
    Each entry maps a type name to its direct supertypes.
    """

    relations: Dict[str, List[str]] = field(default_factory=dict)

    def add_relation(self, subtype: str, supertype: str) -> None:
        """Add a direct subtype relationship."""
        if subtype not in self.relations:
            self.relations[subtype] = []
        if supertype not in self.relations[subtype]:
            self.relations[subtype].append(supertype)

    def get_direct_supertypes(self, type_name: str) -> List[str]:
        """Get immediate supertypes of a type."""
        return self.relations.get(type_name, [])

    def get_all_supertypes(self, type_name: str) -> Set[str]:
        """Get all transitive supertypes of a type (including object)."""
        visited: Set[str] = set()
        queue = [type_name]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for sup in self.get_direct_supertypes(current):
                if sup not in visited:
                    queue.append(sup)
        visited.discard(type_name)
        visited.add("object")
        return visited

    def is_direct_subtype(self, sub: str, sup: str) -> bool:
        """Check if sub is a direct subtype of sup."""
        return sup in self.relations.get(sub, [])

    def is_transitive_subtype(self, sub: str, sup: str) -> bool:
        """Check if sub is a transitive subtype of sup."""
        if sub == sup:
            return True
        return sup in self.get_all_supertypes(sub)


def build_default_hierarchy() -> TypeHierarchy:
    """
    Construct the default type hierarchy.

    Hierarchy:
        object (top)
        +-- number
        |   +-- int
        |   +-- float
        +-- string
        +-- bool
        +-- Animal
        |   +-- Dog
        |   +-- Cat
        +-- Vehicle
            +-- Car
            +-- Truck
    """
    h = TypeHierarchy()

    # Numeric hierarchy
    h.add_relation("int", "float")
    h.add_relation("int", "number")
    h.add_relation("float", "number")
    h.add_relation("number", "object")

    # String and bool
    h.add_relation("string", "object")
    h.add_relation("bool", "object")

    # Animal hierarchy
    h.add_relation("Dog", "Animal")
    h.add_relation("Cat", "Animal")
    h.add_relation("Animal", "object")

    # Vehicle hierarchy
    h.add_relation("Car", "Vehicle")
    h.add_relation("Truck", "Vehicle")
    h.add_relation("Vehicle", "object")

    # Void type
    h.add_relation("void", "object")

    return h


# ============================================================================
# Subtype Check Result
# ============================================================================

@dataclass
class SubtypeResult:
    """Result of a subtype check with explanation trail."""

    is_subtype: bool
    explanation: str = ""
    trail: List[str] = field(default_factory=list)
    checked_pairs: int = 0

    def with_explanation(self, msg: str) -> SubtypeResult:
        """Return a copy with added explanation."""
        return SubtypeResult(
            is_subtype=self.is_subtype,
            explanation=msg,
            trail=self.trail + [msg],
            checked_pairs=self.checked_pairs,
        )


# ============================================================================
# Subtype Checker
# ============================================================================

class SubtypeChecker:
    """
    Core subtype relation implementation.

    Handles all type forms including primitives, functions, generics,
    unions, and the top/bottom types. Uses a configurable type hierarchy
    for named type relationships.
    """

    def __init__(self, hierarchy: Optional[TypeHierarchy] = None) -> None:
        self._hierarchy = hierarchy or build_default_hierarchy()
        self._cache: Dict[Tuple[str, str], bool] = {}
        self._checking: Set[Tuple[str, str]] = set()
        self._check_count: int = 0
        self._cache_hits: int = 0
        self._max_recursion: int = 64
        self._current_depth: int = 0

    def is_subtype(self, t1: TypeNode, t2: TypeNode) -> bool:
        """
        Check if t1 is a subtype of t2 (i.e., t1 <: t2).

        A value of type t1 can be safely used where type t2 is expected
        if and only if t1 <: t2.

        Args:
            t1: The potential subtype
            t2: The potential supertype

        Returns:
            True if t1 is a subtype of t2
        """
        self._check_count += 1
        self._current_depth += 1

        if self._current_depth > self._max_recursion:
            self._current_depth -= 1
            return False

        try:
            # Check cache
            cache_key = (t1.structural_hash(), t2.structural_hash())
            if cache_key in self._cache:
                self._cache_hits += 1
                return self._cache[cache_key]

            # Cycle detection
            if cache_key in self._checking:
                return True  # Assume true for recursive types
            self._checking.add(cache_key)

            result = self._check_subtype_impl(t1, t2)

            # Cache result
            self._cache[cache_key] = result
            self._checking.discard(cache_key)

            return result
        finally:
            self._current_depth -= 1

    def check_with_explanation(self, t1: TypeNode, t2: TypeNode) -> SubtypeResult:
        """
        Check subtype relation with detailed explanation.

        Returns a SubtypeResult with explanation trail showing
        how the decision was reached.
        """
        result = self.is_subtype(t1, t2)
        explanation = self._build_explanation(t1, t2, result)
        return SubtypeResult(
            is_subtype=result,
            explanation=explanation,
            checked_pairs=self._check_count,
        )

    def get_statistics(self) -> Dict[str, int]:
        """Return checker statistics."""
        return {
            "total_checks": self._check_count,
            "cache_hits": self._cache_hits,
            "cache_size": len(self._cache),
        }

    def reset_statistics(self) -> None:
        """Reset checker statistics and cache."""
        self._check_count = 0
        self._cache_hits = 0
        self._cache.clear()
        self._checking.clear()

    def _check_subtype_impl(self, t1: TypeNode, t2: TypeNode) -> bool:
        """Core subtype checking implementation - dispatches to specific handlers."""

        # Reflexivity: T <: T
        if t1 == t2:
            return True

        # Bottom is subtype of everything
        if isinstance(t1, BottomType):
            return True

        # Everything is subtype of Top
        if isinstance(t2, TopType):
            return True

        # Nothing is subtype of Bottom (except Bottom itself, handled above)
        if isinstance(t2, BottomType):
            return False

        # Top is not subtype of anything except itself (handled above)
        if isinstance(t1, TopType):
            return False

        # Union type on the left: all members must be subtypes
        if isinstance(t1, UnionType):
            return self._check_union_left(t1, t2)

        # Union type on the right: t1 must be subtype of at least one member
        if isinstance(t2, UnionType):
            return self._check_union_right(t1, t2)

        # Both primitive types
        if isinstance(t1, PrimitiveType) and isinstance(t2, PrimitiveType):
            return self._check_primitive_subtype(t1, t2)

        # Both function types
        if isinstance(t1, FunctionType) and isinstance(t2, FunctionType):
            return self._check_function_subtype(t1, t2)

        # Both generic types
        if isinstance(t1, GenericType) and isinstance(t2, GenericType):
            return self._check_generic_subtype(t1, t2)

        # Primitive subtype of generic - not allowed
        if isinstance(t1, PrimitiveType) and isinstance(t2, GenericType):
            return False

        # Generic subtype of primitive - not allowed
        if isinstance(t1, GenericType) and isinstance(t2, PrimitiveType):
            return False

        # Function subtype of primitive - only if primitive is object
        if isinstance(t1, FunctionType) and isinstance(t2, PrimitiveType):
            return t2.name == "object"

        # Primitive subtype of function - never
        if isinstance(t1, PrimitiveType) and isinstance(t2, FunctionType):
            return False

        # Generic subtype of function or vice versa - never
        if isinstance(t1, GenericType) and isinstance(t2, FunctionType):
            return False
        if isinstance(t1, FunctionType) and isinstance(t2, GenericType):
            return False

        return False

    def _check_primitive_subtype(self, t1: PrimitiveType, t2: PrimitiveType) -> bool:
        """
        Check if primitive type t1 is a subtype of primitive type t2.

        Uses the configured type hierarchy to determine subtype relationships.
        Handles both direct and transitive subtype relations.
        """
        if t1.name == t2.name:
            return True

        # Use hierarchy for transitive check
        return self._hierarchy.is_transitive_subtype(t1.name, t2.name)

    def _check_function_subtype(self, t1: FunctionType, t2: FunctionType) -> bool:
        """
        Check if function type t1 is a subtype of function type t2.

        For a function type (A1, A2, ...) -> R1 to be a subtype of
        (B1, B2, ...) -> R2, we need:
            - Same number of parameters (arity check)
            - Parameter types are compatible (type-safe substitution)
            - Return type R1 <: R2 (covariant in return type)

        This ensures that a function value of type t1 can safely be used
        wherever a function of type t2 is expected.
        """
        # Arity must match
        if len(t1.param_types) != len(t2.param_types):
            return False

        # Check parameter types are compatible for safe substitution
        for param_t1, param_t2 in zip(t1.param_types, t2.param_types):
            if not self.is_subtype(param_t1, param_t2):
                return False

        # Return type must be covariant: R1 <: R2
        if not self.is_subtype(t1.return_type, t2.return_type):
            return False

        return True

    def _check_generic_subtype(self, t1: GenericType, t2: GenericType) -> bool:
        """
        Check if generic type t1 is a subtype of generic type t2.

        For generic types, we require:
            - Same base type name (e.g., both List, both Map)
            - Same number of type arguments
            - Each type argument is covariantly related: Arg1_i <: Arg2_i

        This implements covariant generics (simplified model, as in many
        practical type systems like Kotlin's declaration-site variance).
        """
        # Must have same base type
        if t1.base_name != t2.base_name:
            return False

        # Must have same number of type arguments
        if len(t1.type_args) != len(t2.type_args):
            return False

        # Check each type argument covariantly
        for arg1, arg2 in zip(t1.type_args, t2.type_args):
            if not self.is_subtype(arg1, arg2):
                return False

        return True

    def _check_union_left(self, t1: UnionType, t2: TypeNode) -> bool:
        """
        Check if a union type is a subtype of another type.

        T1 | T2 | ... | Tn <: T  iff  Ti <: T for all i

        Every member of the union must be a subtype of the target.
        """
        for member in t1.members:
            if not self.is_subtype(member, t2):
                return False
        return True

    def _check_union_right(self, t1: TypeNode, t2: UnionType) -> bool:
        """
        Check if a type is a subtype of a union type.

        T <: T1 | T2 | ... | Tn  iff  T <: Ti for some i

        The source type must be a subtype of at least one union member.
        """
        for member in t2.members:
            if self.is_subtype(t1, member):
                return True
        return False

    def _check_intersection_compatibility(self, t1: TypeNode, t2: TypeNode) -> bool:
        """
        Check if two types have a non-empty intersection.
        Used for determining if a cast between types could possibly succeed.
        """
        if self.is_subtype(t1, t2) or self.is_subtype(t2, t1):
            return True

        if isinstance(t1, UnionType):
            for m in t1.members:
                if self._check_intersection_compatibility(m, t2):
                    return True
            return False

        if isinstance(t2, UnionType):
            for m in t2.members:
                if self._check_intersection_compatibility(t1, m):
                    return True
            return False

        return False

    def _resolve_type_alias(self, t: TypeNode) -> TypeNode:
        """
        Resolve type aliases to their underlying types.
        In this implementation, aliases are resolved during parsing,
        so this is a pass-through. Kept for API compatibility.
        """
        return t

    def _normalize_union(self, t: TypeNode) -> TypeNode:
        """
        Normalize a union type by removing redundant members.

        If T1 <: T2, then T1 | T2 simplifies to T2.
        """
        if not isinstance(t, UnionType):
            return t

        members = list(t.members)
        filtered: List[TypeNode] = []

        for i, m1 in enumerate(members):
            is_redundant = False
            for j, m2 in enumerate(members):
                if i != j and self.is_subtype(m1, m2):
                    is_redundant = True
                    break
            if not is_redundant:
                filtered.append(m1)

        if not filtered:
            return BottomType()
        if len(filtered) == 1:
            return filtered[0]
        return UnionType(members=frozenset(filtered))

    def _compute_join(self, t1: TypeNode, t2: TypeNode) -> TypeNode:
        """
        Compute the least upper bound (join) of two types.
        Used in type inference for conditional expressions.
        """
        if self.is_subtype(t1, t2):
            return t2
        if self.is_subtype(t2, t1):
            return t1
        return UnionType(members=frozenset({t1, t2}))

    def _compute_meet(self, t1: TypeNode, t2: TypeNode) -> TypeNode:
        """
        Compute the greatest lower bound (meet) of two types.
        Used in type narrowing for pattern matching.
        """
        if self.is_subtype(t1, t2):
            return t1
        if self.is_subtype(t2, t1):
            return t2
        return BottomType()

    def _build_explanation(self, t1: TypeNode, t2: TypeNode, result: bool) -> str:
        """Build a human-readable explanation of the subtype check."""
        relation = "<:" if result else "<!:"
        base = f"{t1.display()} {relation} {t2.display()}"

        if result:
            reason = self._explain_success(t1, t2)
        else:
            reason = self._explain_failure(t1, t2)

        return f"{base} -- {reason}"

    def _explain_success(self, t1: TypeNode, t2: TypeNode) -> str:
        """Explain why a subtype check succeeded."""
        if t1 == t2:
            return "reflexivity (same type)"
        if isinstance(t1, BottomType):
            return "bottom is subtype of everything"
        if isinstance(t2, TopType):
            return "everything is subtype of top"
        if isinstance(t1, PrimitiveType) and isinstance(t2, PrimitiveType):
            return f"hierarchy: {t1.name} extends {t2.name}"
        if isinstance(t1, FunctionType) and isinstance(t2, FunctionType):
            return "function types are compatible"
        if isinstance(t1, GenericType) and isinstance(t2, GenericType):
            return f"generic {t1.base_name} type arguments are compatible"
        return "structural compatibility"

    def _explain_failure(self, t1: TypeNode, t2: TypeNode) -> str:
        """Explain why a subtype check failed."""
        if isinstance(t1, PrimitiveType) and isinstance(t2, PrimitiveType):
            return f"no hierarchy path from {t1.name} to {t2.name}"
        if isinstance(t1, FunctionType) and isinstance(t2, FunctionType):
            if len(t1.param_types) != len(t2.param_types):
                return "arity mismatch"
            return "incompatible function signature"
        if isinstance(t1, GenericType) and isinstance(t2, GenericType):
            if t1.base_name != t2.base_name:
                return f"different generic bases: {t1.base_name} vs {t2.base_name}"
            return "incompatible type arguments"
        return f"no subtype relation between {type(t1).__name__} and {type(t2).__name__}"

    def _check_assignability_extended(self, source: TypeNode, target: TypeNode) -> bool:
        """
        Extended assignability check that also considers:
        - Widening conversions for numeric types
        - Implicit coercions defined in the hierarchy
        """
        if self.is_subtype(source, target):
            return True

        # Numeric widening: int can be assigned to float
        if isinstance(source, PrimitiveType) and isinstance(target, PrimitiveType):
            if source.name == "int" and target.name == "float":
                return True

        return False

    def _collect_type_constraints(
        self, t1: TypeNode, t2: TypeNode
    ) -> List[Tuple[TypeNode, TypeNode]]:
        """
        Collect all subtype constraints generated by checking t1 <: t2.
        Used for constraint-based type inference.
        """
        constraints: List[Tuple[TypeNode, TypeNode]] = [(t1, t2)]

        if isinstance(t1, FunctionType) and isinstance(t2, FunctionType):
            if len(t1.param_types) == len(t2.param_types):
                for p1, p2 in zip(t1.param_types, t2.param_types):
                    constraints.append((p1, p2))
                constraints.append((t1.return_type, t2.return_type))

        elif isinstance(t1, GenericType) and isinstance(t2, GenericType):
            if t1.base_name == t2.base_name:
                for a1, a2 in zip(t1.type_args, t2.type_args):
                    constraints.append((a1, a2))

        return constraints

    def _validate_type_well_formed(self, t: TypeNode) -> List[str]:
        """
        Validate that a type is well-formed.
        Returns a list of issues found.
        """
        issues: List[str] = []

        if isinstance(t, FunctionType):
            if t.depth() > 10:
                issues.append(f"Excessively nested function type (depth {t.depth()})")
            for param in t.param_types:
                issues.extend(self._validate_type_well_formed(param))
            issues.extend(self._validate_type_well_formed(t.return_type))

        elif isinstance(t, GenericType):
            expected_arity = {"List": 1, "Set": 1, "Map": 2, "Optional": 1, "Pair": 2}
            if t.base_name in expected_arity:
                if len(t.type_args) != expected_arity[t.base_name]:
                    issues.append(
                        f"{t.base_name} expects {expected_arity[t.base_name]} type args, "
                        f"got {len(t.type_args)}"
                    )
            for arg in t.type_args:
                issues.extend(self._validate_type_well_formed(arg))

        elif isinstance(t, UnionType):
            if len(t.members) < 2:
                issues.append("Union type should have at least 2 members")
            for member in t.members:
                issues.extend(self._validate_type_well_formed(member))

        return issues

    def _compute_type_distance(self, t1: TypeNode, t2: TypeNode) -> int:
        """
        Compute a distance metric between two types.
        Lower distance means more closely related types.
        Used for error message quality (suggesting similar types).
        """
        if t1 == t2:
            return 0
        if self.is_subtype(t1, t2):
            return 1
        if self.is_subtype(t2, t1):
            return 1

        if isinstance(t1, PrimitiveType) and isinstance(t2, PrimitiveType):
            supers1 = self._hierarchy.get_all_supertypes(t1.name)
            supers2 = self._hierarchy.get_all_supertypes(t2.name)
            common = supers1 & supers2
            if common:
                return 2
            return 10

        if isinstance(t1, FunctionType) and isinstance(t2, FunctionType):
            if len(t1.param_types) != len(t2.param_types):
                return 5 + abs(len(t1.param_types) - len(t2.param_types))
            dist = 0
            for p1, p2 in zip(t1.param_types, t2.param_types):
                dist += self._compute_type_distance(p1, p2)
            dist += self._compute_type_distance(t1.return_type, t2.return_type)
            return dist

        if isinstance(t1, GenericType) and isinstance(t2, GenericType):
            if t1.base_name != t2.base_name:
                return 10
            dist = 0
            for a1, a2 in zip(t1.type_args, t2.type_args):
                dist += self._compute_type_distance(a1, a2)
            return dist

        return 20

    def _find_common_supertype(self, types: List[TypeNode]) -> TypeNode:
        """
        Find the least common supertype for a list of types.
        Used in array literal type inference.
        """
        if not types:
            return BottomType()
        if len(types) == 1:
            return types[0]

        result = types[0]
        for t in types[1:]:
            result = self._compute_join(result, t)
        return result

    def _check_type_bounds(
        self, t: TypeNode, lower: TypeNode, upper: TypeNode
    ) -> bool:
        """Check if a type satisfies both lower and upper bounds."""
        return self.is_subtype(lower, t) and self.is_subtype(t, upper)

    def _substitute_type_variable(
        self, t: TypeNode, var_name: str, replacement: TypeNode
    ) -> TypeNode:
        """
        Substitute a type variable with a concrete type.
        Used in generic type instantiation.
        """
        if isinstance(t, PrimitiveType):
            if t.name == var_name and t.category == "type_variable":
                return replacement
            return t

        elif isinstance(t, FunctionType):
            new_params = tuple(
                self._substitute_type_variable(p, var_name, replacement)
                for p in t.param_types
            )
            new_ret = self._substitute_type_variable(t.return_type, var_name, replacement)
            return FunctionType(param_types=new_params, return_type=new_ret)

        elif isinstance(t, GenericType):
            new_args = tuple(
                self._substitute_type_variable(a, var_name, replacement)
                for a in t.type_args
            )
            return GenericType(base_name=t.base_name, type_args=new_args)

        elif isinstance(t, UnionType):
            new_members = frozenset(
                self._substitute_type_variable(m, var_name, replacement)
                for m in t.members
            )
            return UnionType(members=new_members)

        return t

    def _instantiate_generic(
        self, generic_type: GenericType, bindings: Dict[str, TypeNode]
    ) -> TypeNode:
        """
        Instantiate a generic type with concrete type bindings.
        """
        result: TypeNode = generic_type
        for var_name, concrete_type in bindings.items():
            result = self._substitute_type_variable(result, var_name, concrete_type)
        return result
