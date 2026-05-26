"""
Assignment Validator
====================

Validates type assignments in program specifications by leveraging the
subtype checker. For each assignment statement, determines whether the
source type can be safely assigned to the target type.

Provides:
    - Per-assignment validation results with confidence scores
    - Detailed error messages for invalid assignments
    - Batch validation with summary statistics
    - Assignment categorization (trivial, structural, complex)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .checker import SubtypeChecker, SubtypeResult, TypeHierarchy, build_default_hierarchy
from .parser import AssignmentStatement, ProgramSpec
from .types import (
    BottomType,
    FunctionType,
    GenericType,
    PrimitiveType,
    TopType,
    TypeNode,
    UnionType,
    type_complexity,
)


# ============================================================================
# Validation Result Types
# ============================================================================

@dataclass
class AssignmentValidationResult:
    """Result of validating a single assignment."""

    assignment_id: str
    target_variable: str
    target_type_display: str
    source_expression: str
    source_type_display: str
    is_valid: bool
    confidence: float
    explanation: str
    category: str
    check_time_ms: float = 0.0
    subtype_detail: Optional[SubtypeResult] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "assignment_id": self.assignment_id,
            "target_variable": self.target_variable,
            "target_type": self.target_type_display,
            "source_expression": self.source_expression,
            "source_type": self.source_type_display,
            "is_valid": self.is_valid,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "category": self.category,
            "check_time_ms": round(self.check_time_ms, 3),
        }


@dataclass
class ProgramValidationResult:
    """Result of validating all assignments in a program."""

    program_name: str
    total_assignments: int
    valid_count: int
    invalid_count: int
    assignments: List[AssignmentValidationResult] = field(default_factory=list)
    validation_time_ms: float = 0.0
    warnings: List[str] = field(default_factory=list)

    @property
    def validity_ratio(self) -> float:
        """Proportion of valid assignments."""
        if self.total_assignments == 0:
            return 0.0
        return self.valid_count / self.total_assignments

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "program_name": self.program_name,
            "total_assignments": self.total_assignments,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "validity_ratio": round(self.validity_ratio, 4),
            "validation_time_ms": round(self.validation_time_ms, 3),
            "assignments": [a.to_dict() for a in self.assignments],
            "warnings": self.warnings,
        }


# ============================================================================
# Assignment Categorizer
# ============================================================================

class AssignmentCategorizer:
    """
    Categorizes assignments by their structural complexity.
    Used for reporting and difficulty estimation.
    """

    CATEGORY_TRIVIAL = "trivial"
    CATEGORY_PRIMITIVE = "primitive_hierarchy"
    CATEGORY_FUNCTION_SIMPLE = "function_simple"
    CATEGORY_FUNCTION_HIGHER_ORDER = "function_higher_order"
    CATEGORY_GENERIC = "generic_container"
    CATEGORY_UNION = "union_type"
    CATEGORY_COMPLEX = "complex_mixed"

    def categorize(self, source: TypeNode, target: TypeNode) -> str:
        """Determine the category of an assignment based on involved types."""
        source_complexity = type_complexity(source)
        target_complexity = type_complexity(target)
        total_complexity = source_complexity + target_complexity

        # Same type - trivial
        if source == target:
            return self.CATEGORY_TRIVIAL

        # Both primitive
        if isinstance(source, PrimitiveType) and isinstance(target, PrimitiveType):
            return self.CATEGORY_PRIMITIVE

        # Function types involved
        if isinstance(source, FunctionType) or isinstance(target, FunctionType):
            if total_complexity > 8:
                return self.CATEGORY_FUNCTION_HIGHER_ORDER
            return self.CATEGORY_FUNCTION_SIMPLE

        # Generic types involved
        if isinstance(source, GenericType) or isinstance(target, GenericType):
            return self.CATEGORY_GENERIC

        # Union types involved
        if isinstance(source, UnionType) or isinstance(target, UnionType):
            return self.CATEGORY_UNION

        # High complexity
        if total_complexity > 10:
            return self.CATEGORY_COMPLEX

        return self.CATEGORY_TRIVIAL

    def compute_confidence(self, category: str, is_valid: bool) -> float:
        """
        Compute confidence score based on category and result.
        Higher confidence for simpler checks.
        """
        base_confidence = {
            self.CATEGORY_TRIVIAL: 1.0,
            self.CATEGORY_PRIMITIVE: 0.98,
            self.CATEGORY_FUNCTION_SIMPLE: 0.95,
            self.CATEGORY_FUNCTION_HIGHER_ORDER: 0.90,
            self.CATEGORY_GENERIC: 0.95,
            self.CATEGORY_UNION: 0.92,
            self.CATEGORY_COMPLEX: 0.85,
        }
        return base_confidence.get(category, 0.80)


# ============================================================================
# Assignment Validator
# ============================================================================

class AssignmentValidator:
    """
    Main validator class that processes program specs and validates
    all assignment statements.
    """

    def __init__(self, hierarchy: Optional[TypeHierarchy] = None) -> None:
        self._checker = SubtypeChecker(hierarchy or build_default_hierarchy())
        self._categorizer = AssignmentCategorizer()
        self._total_validated: int = 0
        self._total_valid: int = 0
        self._total_invalid: int = 0

    def validate_program(self, spec: ProgramSpec) -> ProgramValidationResult:
        """
        Validate all assignments in a program specification.

        For each assignment, checks whether the source type is a subtype
        of the target type, which determines if the assignment is valid.
        """
        start_time = time.time()
        results: List[AssignmentValidationResult] = []
        valid_count = 0
        invalid_count = 0
        warnings: List[str] = []

        for idx, assignment in enumerate(spec.assignments):
            assign_result = self._validate_single_assignment(
                assignment, f"{spec.name}_assign_{idx}"
            )
            results.append(assign_result)

            if assign_result.is_valid:
                valid_count += 1
            else:
                invalid_count += 1

        elapsed = (time.time() - start_time) * 1000

        self._total_validated += len(spec.assignments)
        self._total_valid += valid_count
        self._total_invalid += invalid_count

        if spec.parse_warnings:
            warnings.extend(spec.parse_warnings)

        return ProgramValidationResult(
            program_name=spec.name,
            total_assignments=len(spec.assignments),
            valid_count=valid_count,
            invalid_count=invalid_count,
            assignments=results,
            validation_time_ms=elapsed,
            warnings=warnings,
        )

    def validate_multiple(self, specs: List[ProgramSpec]) -> List[ProgramValidationResult]:
        """Validate multiple program specs."""
        return [self.validate_program(spec) for spec in specs]

    def get_statistics(self) -> Dict[str, Any]:
        """Return validation statistics."""
        return {
            "total_validated": self._total_validated,
            "total_valid": self._total_valid,
            "total_invalid": self._total_invalid,
            "checker_stats": self._checker.get_statistics(),
        }

    def _validate_single_assignment(
        self, assignment: AssignmentStatement, assign_id: str
    ) -> AssignmentValidationResult:
        """Validate a single assignment statement."""
        start = time.time()

        source_type = assignment.source_type
        target_type = assignment.target_type

        # Categorize the assignment
        category = self._categorizer.categorize(source_type, target_type)

        # Perform the subtype check
        subtype_result = self._checker.check_with_explanation(source_type, target_type)
        is_valid = subtype_result.is_subtype

        # Compute confidence
        confidence = self._categorizer.compute_confidence(category, is_valid)

        # Build explanation
        if is_valid:
            explanation = self._build_valid_explanation(
                assignment, source_type, target_type, category
            )
        else:
            explanation = self._build_invalid_explanation(
                assignment, source_type, target_type, category
            )

        elapsed = (time.time() - start) * 1000

        return AssignmentValidationResult(
            assignment_id=assign_id,
            target_variable=assignment.target_variable,
            target_type_display=target_type.display(),
            source_expression=assignment.source_expression,
            source_type_display=source_type.display(),
            is_valid=is_valid,
            confidence=confidence,
            explanation=explanation,
            category=category,
            check_time_ms=elapsed,
            subtype_detail=subtype_result,
        )

    def _build_valid_explanation(
        self,
        assignment: AssignmentStatement,
        source: TypeNode,
        target: TypeNode,
        category: str,
    ) -> str:
        """Build explanation for a valid assignment."""
        base = f"Assignment '{assignment.target_variable} = {assignment.source_expression}' is valid"

        if source == target:
            return f"{base}: identical types"

        if isinstance(source, PrimitiveType) and isinstance(target, PrimitiveType):
            return f"{base}: {source.name} is a subtype of {target.name} in the type hierarchy"

        if isinstance(source, FunctionType) and isinstance(target, FunctionType):
            return f"{base}: function types are compatible (parameter and return types align)"

        if isinstance(source, GenericType) and isinstance(target, GenericType):
            return f"{base}: generic container types are compatible"

        return f"{base}: source type is assignable to target type ({category})"

    def _build_invalid_explanation(
        self,
        assignment: AssignmentStatement,
        source: TypeNode,
        target: TypeNode,
        category: str,
    ) -> str:
        """Build explanation for an invalid assignment."""
        base = (
            f"Assignment '{assignment.target_variable} = {assignment.source_expression}' "
            f"is invalid"
        )

        if isinstance(source, PrimitiveType) and isinstance(target, PrimitiveType):
            return (
                f"{base}: {source.name} is not a subtype of {target.name} "
                f"in the type hierarchy"
            )

        if isinstance(source, FunctionType) and isinstance(target, FunctionType):
            if len(source.param_types) != len(target.param_types):
                return f"{base}: function arity mismatch ({len(source.param_types)} vs {len(target.param_types)} parameters)"
            return f"{base}: function type signature is incompatible"

        if isinstance(source, GenericType) and isinstance(target, GenericType):
            if source.base_name != target.base_name:
                return f"{base}: incompatible container types ({source.base_name} vs {target.base_name})"
            return f"{base}: incompatible type arguments in {source.base_name}"

        return f"{base}: {source.display()} is not assignable to {target.display()}"


# ============================================================================
# Convenience Functions
# ============================================================================

def validate_assignment_quick(
    source_type: TypeNode, target_type: TypeNode
) -> bool:
    """Quick validation without detailed results."""
    checker = SubtypeChecker(build_default_hierarchy())
    return checker.is_subtype(source_type, target_type)


def validate_program_from_spec(spec: ProgramSpec) -> ProgramValidationResult:
    """Validate a program spec using default configuration."""
    validator = AssignmentValidator()
    return validator.validate_program(spec)
