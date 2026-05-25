"""Constraint solver for type variable bounds.

Collects type constraints from various scopes and resolves type variable
bounds. Constraints are scoped (global, function-level) and the solver
determines the effective bound for each type variable at each scope level.

Resolution uses priority ordering to determine which constraints take
precedence when multiple constraints exist for the same type variable.
"""


class ConstraintSolver:
    """Resolves type variable constraints within scoped contexts."""

    def __init__(self):
        self._constraints = {}  # scope -> {type_var -> bound_info}

    def collect_constraints(self, records):
        """Collect type constraints from parsed records.

        Groups constraints by scope and type variable. For each scope,
        tracks the bound and priority of each constraint encountered.
        Note: seq is local to each stream, so ordering across modules
        requires the source_module as a secondary key.
        """
        # Sort records by priority for deterministic processing
        sorted_records = sorted(
            [r for r in records if r.kind == "constraint"],
            key=lambda r: (r.priority, r.seq),
        )

        for record in sorted_records:
            scope = record.scope
            type_var = record.type_var

            if scope not in self._constraints:
                self._constraints[scope] = {}

            if type_var not in self._constraints[scope]:
                self._constraints[scope][type_var] = {
                    "bound": record.bound,
                    "priority": record.priority,
                    "source_module": record.source_module,
                }
            else:
                # Higher priority constraint overrides lower
                existing = self._constraints[scope][type_var]
                existing["bound"] += f",{record.bound}"
                existing["priority"] += record.priority

    def resolve(self, type_var, scope):
        """Resolve the effective bound for a type variable in a given scope.

        Uses scope-specific constraints if available. The resolved bound
        is the accumulated result of all constraints in that scope.
        """
        if scope in self._constraints and type_var in self._constraints[scope]:
            info = self._constraints[scope][type_var]
            return {
                "type_var": type_var,
                "scope": scope,
                "resolved_bound": info["bound"],
                "priority": info["priority"],
                "source_module": info["source_module"],
            }
        # Fall back to global scope
        if "global" in self._constraints and type_var in self._constraints["global"]:
            info = self._constraints["global"][type_var]
            return {
                "type_var": type_var,
                "scope": "global",
                "resolved_bound": info["bound"],
                "priority": info["priority"],
                "source_module": info["source_module"],
            }
        return None

    def get_all_resolutions(self):
        """Return all resolved constraints across all scopes."""
        results = []
        for scope, variables in self._constraints.items():
            for type_var, info in variables.items():
                results.append({
                    "type_var": type_var,
                    "scope": scope,
                    "resolved_bound": info["bound"],
                    "priority": info["priority"],
                    "source_module": info["source_module"],
                })
        return results
