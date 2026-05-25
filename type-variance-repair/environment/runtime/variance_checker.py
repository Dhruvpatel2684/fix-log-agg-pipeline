"""Variance-aware type assignability checker.

Implements subtype checking with variance rules for generic types:
- Covariant types (producers): subtype relationship preserved
- Contravariant types (consumers): subtype relationship reversed
- Invariant types: exact match required

The checker builds a type hierarchy and validates that all type assignments
respect the declared variance of their generic containers.
"""
import configparser
import re


class VarianceChecker:
    """Checks type assignability with respect to declared variance positions."""

    def __init__(self, config_path):
        self._config = configparser.ConfigParser()
        self._config.read(config_path)
        self._max_depth = self._config.getint("checker.bounds", "max_recursion_depth")
        self._type_hierarchy = {}  # name -> parent
        self._generic_types = {}  # name -> {"type_param": ..., "variance": ...}
        self._current_depth = 0

    def register_types(self, records):
        """Register type declarations and generic type info from parsed records."""
        for record in records:
            if record.kind == "type_decl":
                self._type_hierarchy[record.name] = record.parent
            elif record.kind == "generic_decl":
                self._generic_types[record.name] = {
                    "type_param": record.type_param,
                    "variance": record.variance,
                }

    def is_subtype(self, sub, sup):
        """Check if 'sub' is a subtype of 'sup' in the type hierarchy.

        Traverses the inheritance chain upward from sub to check if sup
        is an ancestor. Returns True if sub == sup or sub extends sup.
        """
        if sub == sup:
            return True
        self._current_depth += 1
        if self._current_depth > self._max_depth:
            self._current_depth -= 1
            return False
        current = sub
        visited = set()
        while current is not None:
            if current == sup:
                self._current_depth -= 1
                return True
            if current in visited:
                break
            visited.add(current)
            current = self._type_hierarchy.get(current)
        self._current_depth -= 1
        return False

    def check_assignment(self, target_type, source_type, context=None):
        """Check if source_type can be assigned to target_type.

        For simple types: source must be subtype of target.
        For generic types: applies variance rules based on the assignment
        context position to determine subtyping direction.

        Returns a dict with 'valid' (bool) and 'reason' (str).
        """
        # Parse generic types: e.g., "Producer<Cat>" -> ("Producer", "Cat")
        target_generic = self._parse_generic(target_type)
        source_generic = self._parse_generic(source_type)

        if target_generic and source_generic:
            target_container, target_arg = target_generic
            source_container, source_arg = source_generic

            # Containers must match
            if target_container != source_container:
                return {
                    "valid": False,
                    "reason": f"container mismatch: {target_container} vs {source_container}",
                }

            # Get variance declaration for this container
            generic_info = self._generic_types.get(target_container)
            if generic_info is None:
                return {
                    "valid": False,
                    "reason": f"unknown generic type: {target_container}",
                }

            variance = generic_info["variance"]
            return self._check_variance_assignability(
                variance, target_arg, source_arg, context
            )

        # Simple type assignment: source must be subtype of target
        if self.is_subtype(source_type, target_type):
            return {"valid": True, "reason": "direct subtype"}
        return {
            "valid": False,
            "reason": f"{source_type} is not a subtype of {target_type}",
        }

    def _check_variance_assignability(self, variance, target_arg, source_arg, context):
        """Apply variance-specific assignability rules.

        Uses the assignment context to determine the variance position.
        In use-site variance, the position where the type appears (parameter
        position = input = contravariant, return position = output = covariant)
        determines the subtyping direction regardless of the declared variance.
        """
        self._current_depth += 1
        if self._current_depth > self._max_depth:
            self._current_depth -= 1
            return {"valid": False, "reason": "max recursion depth exceeded"}

        # Determine effective variance from the usage context:
        # parameter positions are input (contravariant direction)
        # return_value positions are output (covariant direction)
        # local_bind requires exact match (invariant)
        if context == "return_value":
            effective_variance = "covariant"
        elif context == "parameter":
            effective_variance = "contravariant"
        else:
            effective_variance = "invariant"

        if effective_variance == "covariant":
            # Output position: source arg must be subtype of target arg
            valid = self.is_subtype(source_arg, target_arg)
            self._current_depth -= 1
            if valid:
                return {"valid": True, "reason": "covariant: subtype preserved"}
            return {
                "valid": False,
                "reason": f"covariant violation: {source_arg} is not subtype of {target_arg}",
            }

        elif effective_variance == "contravariant":
            # Input position: target arg must be subtype of source arg
            valid = self.is_subtype(target_arg, source_arg)
            self._current_depth -= 1
            if valid:
                return {"valid": True, "reason": "contravariant: subtype reversed"}
            return {
                "valid": False,
                "reason": f"contravariant violation: {target_arg} is not subtype of {source_arg}",
            }

        else:
            # Local binding: exact type match required
            valid = target_arg == source_arg
            self._current_depth -= 1
            if valid:
                return {"valid": True, "reason": "invariant: exact match"}
            return {
                "valid": False,
                "reason": f"invariant violation: {target_arg} != {source_arg}",
            }

    def _parse_generic(self, type_str):
        """Parse a generic type string like 'Producer<Cat>' into ('Producer', 'Cat')."""
        match = re.match(r"^(\w+)<(\w+)>$", type_str)
        if match:
            return match.group(1), match.group(2)
        return None
