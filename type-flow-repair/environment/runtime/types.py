"""
Type Representations for the Gradual Type System
=================================================

This module defines the core type structures used throughout the type checking
system. Each type is represented as an immutable object with support for
equality comparison, hashing, serialization, and pretty-printing.

Type Hierarchy:
    TypeNode (abstract base)
    ├── PrimitiveType      - int, float, string, bool, named types
    ├── FunctionType       - (ParamTypes) -> ReturnType
    ├── GenericType        - List[T], Map[K,V], Set[T]
    ├── UnionType          - T1 | T2 | ... | Tn
    ├── TopType            - object (universal supertype)
    └── BottomType         - never (universal subtype)
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple


# ============================================================================
# Abstract Base
# ============================================================================

class TypeNode(ABC):
    """Abstract base class for all type representations."""

    @abstractmethod
    def display(self) -> str:
        """Human-readable string representation of the type."""
        ...

    @abstractmethod
    def serialize(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        ...

    @abstractmethod
    def structural_hash(self) -> str:
        """Compute a stable structural hash for caching."""
        ...

    @abstractmethod
    def contains_type(self, target: TypeNode) -> bool:
        """Check if this type structurally contains the target type."""
        ...

    @abstractmethod
    def depth(self) -> int:
        """Compute the nesting depth of this type."""
        ...

    @abstractmethod
    def type_variables(self) -> FrozenSet[str]:
        """Return all free type variable names in this type."""
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.display()})"

    def __str__(self) -> str:
        return self.display()


# ============================================================================
# Primitive Types
# ============================================================================

@dataclass(frozen=True)
class PrimitiveType(TypeNode):
    """
    Represents a primitive or named type in the type hierarchy.

    Examples: int, float, string, bool, Animal, Dog, Cat, Vehicle, Car, Truck
    """

    name: str
    category: str = "primitive"
    metadata: Dict[str, str] = field(default_factory=dict, hash=False, compare=False)

    def display(self) -> str:
        return self.name

    def serialize(self) -> Dict[str, Any]:
        result = {
            "kind": "primitive",
            "name": self.name,
            "category": self.category,
        }
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result

    def structural_hash(self) -> str:
        raw = f"primitive:{self.name}:{self.category}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def contains_type(self, target: TypeNode) -> bool:
        if isinstance(target, PrimitiveType):
            return self.name == target.name
        return False

    def depth(self) -> int:
        return 0

    def type_variables(self) -> FrozenSet[str]:
        return frozenset()

    def is_numeric(self) -> bool:
        """Check if this primitive is a numeric type."""
        return self.name in ("int", "float", "number")

    def is_boolean(self) -> bool:
        """Check if this primitive is boolean."""
        return self.name == "bool"

    def qualified_name(self) -> str:
        """Return fully qualified name including category."""
        if self.category == "primitive":
            return self.name
        return f"{self.category}.{self.name}"


# ============================================================================
# Function Types
# ============================================================================

@dataclass(frozen=True)
class FunctionType(TypeNode):
    """
    Represents a function type with parameter types and a return type.

    Example: (int, string) -> bool represents a function taking an int and
    a string parameter and returning a bool.

    Function types support higher-order functions:
        ((int) -> float) -> string
    represents a function that takes a function (int -> float) as parameter
    and returns a string.
    """

    param_types: Tuple[TypeNode, ...]
    return_type: TypeNode
    is_variadic: bool = False
    label: str = ""

    def display(self) -> str:
        params = ", ".join(p.display() for p in self.param_types)
        if self.is_variadic:
            params += "..."
        ret = self.return_type.display()
        base = f"({params}) -> {ret}"
        if self.label:
            return f"{self.label}:{base}"
        return base

    def serialize(self) -> Dict[str, Any]:
        result = {
            "kind": "function",
            "params": [p.serialize() for p in self.param_types],
            "return": self.return_type.serialize(),
        }
        if self.is_variadic:
            result["variadic"] = True
        if self.label:
            result["label"] = self.label
        return result

    def structural_hash(self) -> str:
        param_hashes = "|".join(p.structural_hash() for p in self.param_types)
        ret_hash = self.return_type.structural_hash()
        raw = f"function:({param_hashes})->{ret_hash}:v={self.is_variadic}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def contains_type(self, target: TypeNode) -> bool:
        if self == target:
            return True
        for param in self.param_types:
            if param.contains_type(target):
                return True
        return self.return_type.contains_type(target)

    def depth(self) -> int:
        param_depths = [p.depth() for p in self.param_types] if self.param_types else [0]
        return 1 + max(max(param_depths), self.return_type.depth())

    def type_variables(self) -> FrozenSet[str]:
        result: set = set()
        for p in self.param_types:
            result |= p.type_variables()
        result |= self.return_type.type_variables()
        return frozenset(result)

    def arity(self) -> int:
        """Return the number of parameters."""
        return len(self.param_types)

    def with_return_type(self, new_return: TypeNode) -> FunctionType:
        """Create a new function type with a different return type."""
        return FunctionType(
            param_types=self.param_types,
            return_type=new_return,
            is_variadic=self.is_variadic,
            label=self.label,
        )

    def curried_form(self) -> TypeNode:
        """Convert multi-param function to curried form."""
        if len(self.param_types) <= 1:
            return self
        result: TypeNode = self.return_type
        for param in reversed(self.param_types):
            result = FunctionType(param_types=(param,), return_type=result)
        return result


# ============================================================================
# Generic Container Types
# ============================================================================

@dataclass(frozen=True)
class GenericType(TypeNode):
    """
    Represents a generic container type with type arguments.

    Examples:
        List[int]       -> GenericType("List", (PrimitiveType("int"),))
        Map[string,int] -> GenericType("Map", (PrimitiveType("string"), PrimitiveType("int")))
        Set[float]      -> GenericType("Set", (PrimitiveType("float"),))
    """

    base_name: str
    type_args: Tuple[TypeNode, ...]
    variance_annotations: Tuple[str, ...] = ()

    def display(self) -> str:
        args = ", ".join(a.display() for a in self.type_args)
        return f"{self.base_name}[{args}]"

    def serialize(self) -> Dict[str, Any]:
        result = {
            "kind": "generic",
            "base": self.base_name,
            "args": [a.serialize() for a in self.type_args],
        }
        if self.variance_annotations:
            result["variance"] = list(self.variance_annotations)
        return result

    def structural_hash(self) -> str:
        arg_hashes = "|".join(a.structural_hash() for a in self.type_args)
        raw = f"generic:{self.base_name}[{arg_hashes}]"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def contains_type(self, target: TypeNode) -> bool:
        if self == target:
            return True
        for arg in self.type_args:
            if arg.contains_type(target):
                return True
        return False

    def depth(self) -> int:
        if not self.type_args:
            return 1
        return 1 + max(a.depth() for a in self.type_args)

    def type_variables(self) -> FrozenSet[str]:
        result: set = set()
        for a in self.type_args:
            result |= a.type_variables()
        return frozenset(result)

    def element_type(self) -> Optional[TypeNode]:
        """For single-argument generics, return the element type."""
        if len(self.type_args) == 1:
            return self.type_args[0]
        return None

    def key_type(self) -> Optional[TypeNode]:
        """For Map types, return the key type."""
        if self.base_name == "Map" and len(self.type_args) >= 1:
            return self.type_args[0]
        return None

    def value_type(self) -> Optional[TypeNode]:
        """For Map types, return the value type."""
        if self.base_name == "Map" and len(self.type_args) >= 2:
            return self.type_args[1]
        return None

    def with_type_args(self, new_args: Tuple[TypeNode, ...]) -> GenericType:
        """Create a new generic type with different type arguments."""
        return GenericType(
            base_name=self.base_name,
            type_args=new_args,
            variance_annotations=self.variance_annotations,
        )


# ============================================================================
# Union Types
# ============================================================================

@dataclass(frozen=True)
class UnionType(TypeNode):
    """
    Represents a union of multiple types: T1 | T2 | ... | Tn

    A value of union type can be any one of the constituent types.
    Union types are normalized: duplicates removed, sorted by display name,
    nested unions flattened.
    """

    members: FrozenSet[TypeNode]
    source_annotation: str = ""

    def display(self) -> str:
        sorted_members = sorted(self.members, key=lambda m: m.display())
        return " | ".join(m.display() for m in sorted_members)

    def serialize(self) -> Dict[str, Any]:
        result = {
            "kind": "union",
            "members": [m.serialize() for m in sorted(self.members, key=lambda x: x.display())],
        }
        if self.source_annotation:
            result["annotation"] = self.source_annotation
        return result

    def structural_hash(self) -> str:
        member_hashes = sorted(m.structural_hash() for m in self.members)
        raw = f"union:{'+'.join(member_hashes)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def contains_type(self, target: TypeNode) -> bool:
        if self == target:
            return True
        for member in self.members:
            if member.contains_type(target):
                return True
        return False

    def depth(self) -> int:
        if not self.members:
            return 0
        return max(m.depth() for m in self.members)

    def type_variables(self) -> FrozenSet[str]:
        result: set = set()
        for m in self.members:
            result |= m.type_variables()
        return frozenset(result)

    def member_count(self) -> int:
        """Return the number of members in the union."""
        return len(self.members)

    def has_member(self, t: TypeNode) -> bool:
        """Check if a specific type is a member of this union."""
        return t in self.members

    def without_member(self, t: TypeNode) -> TypeNode:
        """Remove a member from the union, simplifying if needed."""
        remaining = self.members - {t}
        if len(remaining) == 0:
            return BottomType()
        if len(remaining) == 1:
            return next(iter(remaining))
        return UnionType(members=remaining)


# ============================================================================
# Top and Bottom Types
# ============================================================================

@dataclass(frozen=True)
class TopType(TypeNode):
    """
    The universal supertype (object).
    Every type is a subtype of TopType.
    """

    label: str = "object"

    def display(self) -> str:
        return self.label

    def serialize(self) -> Dict[str, Any]:
        return {"kind": "top", "label": self.label}

    def structural_hash(self) -> str:
        return hashlib.sha256(b"top:object").hexdigest()[:16]

    def contains_type(self, target: TypeNode) -> bool:
        return isinstance(target, TopType)

    def depth(self) -> int:
        return 0

    def type_variables(self) -> FrozenSet[str]:
        return frozenset()


@dataclass(frozen=True)
class BottomType(TypeNode):
    """
    The universal subtype (never/nothing).
    BottomType is a subtype of every type.
    """

    label: str = "never"

    def display(self) -> str:
        return self.label

    def serialize(self) -> Dict[str, Any]:
        return {"kind": "bottom", "label": self.label}

    def structural_hash(self) -> str:
        return hashlib.sha256(b"bottom:never").hexdigest()[:16]

    def contains_type(self, target: TypeNode) -> bool:
        return isinstance(target, BottomType)

    def depth(self) -> int:
        return 0

    def type_variables(self) -> FrozenSet[str]:
        return frozenset()


# ============================================================================
# Type Construction Utilities
# ============================================================================

class TypeFactory:
    """
    Factory class for convenient type construction.
    Provides caching and normalization of constructed types.
    """

    _cache: Dict[str, TypeNode] = {}

    @classmethod
    def primitive(cls, name: str, category: str = "primitive") -> PrimitiveType:
        """Create or retrieve a cached primitive type."""
        key = f"prim:{name}:{category}"
        if key not in cls._cache:
            cls._cache[key] = PrimitiveType(name=name, category=category)
        return cls._cache[key]  # type: ignore

    @classmethod
    def function(cls, params: Sequence[TypeNode], ret: TypeNode) -> FunctionType:
        """Create a function type."""
        return FunctionType(param_types=tuple(params), return_type=ret)

    @classmethod
    def generic(cls, base: str, args: Sequence[TypeNode]) -> GenericType:
        """Create a generic container type."""
        return GenericType(base_name=base, type_args=tuple(args))

    @classmethod
    def union(cls, *members: TypeNode) -> TypeNode:
        """Create a normalized union type, flattening nested unions."""
        flat: set = set()
        for m in members:
            if isinstance(m, UnionType):
                flat |= m.members
            elif isinstance(m, BottomType):
                continue
            elif isinstance(m, TopType):
                return TopType()
            else:
                flat.add(m)
        if len(flat) == 0:
            return BottomType()
        if len(flat) == 1:
            return next(iter(flat))
        return UnionType(members=frozenset(flat))

    @classmethod
    def top(cls) -> TopType:
        """Return the top type (object)."""
        return TopType()

    @classmethod
    def bottom(cls) -> BottomType:
        """Return the bottom type (never)."""
        return BottomType()

    @classmethod
    def void(cls) -> PrimitiveType:
        """Return the void type for function returns."""
        return cls.primitive("void", "special")

    @classmethod
    def list_of(cls, element: TypeNode) -> GenericType:
        """Convenience: create List[element]."""
        return cls.generic("List", [element])

    @classmethod
    def map_of(cls, key: TypeNode, value: TypeNode) -> GenericType:
        """Convenience: create Map[key, value]."""
        return cls.generic("Map", [key, value])

    @classmethod
    def set_of(cls, element: TypeNode) -> GenericType:
        """Convenience: create Set[element]."""
        return cls.generic("Set", [element])

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the type construction cache."""
        cls._cache.clear()


# ============================================================================
# Type Serialization and Deserialization
# ============================================================================

def serialize_type(t: TypeNode) -> Dict[str, Any]:
    """Serialize a type node to a JSON-compatible dictionary."""
    return t.serialize()


def deserialize_type(data: Dict[str, Any]) -> TypeNode:
    """Deserialize a type node from a JSON-compatible dictionary."""
    kind = data.get("kind", "")

    if kind == "primitive":
        return PrimitiveType(
            name=data["name"],
            category=data.get("category", "primitive"),
        )
    elif kind == "function":
        params = tuple(deserialize_type(p) for p in data["params"])
        ret = deserialize_type(data["return"])
        return FunctionType(
            param_types=params,
            return_type=ret,
            is_variadic=data.get("variadic", False),
            label=data.get("label", ""),
        )
    elif kind == "generic":
        args = tuple(deserialize_type(a) for a in data["args"])
        return GenericType(
            base_name=data["base"],
            type_args=args,
        )
    elif kind == "union":
        members = frozenset(deserialize_type(m) for m in data["members"])
        return UnionType(members=members)
    elif kind == "top":
        return TopType(label=data.get("label", "object"))
    elif kind == "bottom":
        return BottomType(label=data.get("label", "never"))
    else:
        raise ValueError(f"Unknown type kind: {kind}")


# ============================================================================
# Type Comparison Utilities
# ============================================================================

def types_equal(t1: TypeNode, t2: TypeNode) -> bool:
    """Deep structural equality check for types."""
    if type(t1) != type(t2):
        return False
    return t1 == t2


def type_complexity(t: TypeNode) -> int:
    """
    Compute a complexity score for a type.
    Used for ordering and optimization in the checker.
    """
    if isinstance(t, (PrimitiveType, TopType, BottomType)):
        return 1
    elif isinstance(t, FunctionType):
        return 2 + sum(type_complexity(p) for p in t.param_types) + type_complexity(t.return_type)
    elif isinstance(t, GenericType):
        return 2 + sum(type_complexity(a) for a in t.type_args)
    elif isinstance(t, UnionType):
        return 1 + sum(type_complexity(m) for m in t.members)
    return 1


def flatten_union(t: TypeNode) -> List[TypeNode]:
    """Flatten a potentially nested union into a list of non-union types."""
    if isinstance(t, UnionType):
        result = []
        for m in t.members:
            result.extend(flatten_union(m))
        return result
    return [t]


def common_supertype_candidates(types: Sequence[TypeNode]) -> List[TypeNode]:
    """
    Find potential common supertypes for a collection of types.
    Used in type inference for join operations.
    """
    if not types:
        return [BottomType()]
    if len(types) == 1:
        return [types[0]]

    candidates: List[TypeNode] = []
    all_primitive = all(isinstance(t, PrimitiveType) for t in types)

    if all_primitive:
        names = {t.name for t in types}  # type: ignore
        if names <= {"int", "float", "number"}:
            candidates.append(PrimitiveType(name="number"))
        candidates.append(TopType())
    else:
        candidates.append(TypeFactory.union(*types))
        candidates.append(TopType())

    return candidates
