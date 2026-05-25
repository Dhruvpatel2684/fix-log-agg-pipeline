"""Constraint solver for type variable bounds.

Collects type constraints from various scopes and resolves type variable
bounds using lattice operations on the type hierarchy.

When multiple constraints exist for the same type variable within a scope,
the solver computes the effective bound by selecting the most general type
that satisfies all constraints (upper bound in the type lattice).
"""


class ConstraintSolver:
    """Resolves type variable constraints within scoped contexts using lattice ops."""

    def __init__(self, type_hierarchy):
        self._constraints = {}  # scope -> {type_var -> [bound_records]}
        self._hierarchy = type_hierarchy  # name -> parent

    def collect_constraints(self, records):
        """Collect type constraints from parsed records.

        Groups constraints by scope and type variable. Multiple constraints
        for the same variable in the same scope are accumulated for
        lattice-based resolution.
        """
        constraint_records = sorted(
            [r for r in records if r.kind == "constraint"],
            key=lambda r: (r.scope, r.type_var, r.priority),
        )

        for record in constraint_records:
            scope = record.scope
            type_var = record.type_var

            if scope not in self._constraints:
                self._constraints[scope] = {}

            if type_var not in self._constraints[scope]:
                self._constraints[scope][type_var] = []

            self._constraints[scope][type_var].append({
                "bound": record.bound,
                "priority": record.priority,
                "source_module": record.source_module,
            })

    def _depth_of(self, type_name):
        """Compute depth of a type in the hierarchy (root = 0)."""
        depth = 0
        current = type_name
        visited = set()
        while current is not None and current not in visited:
            visited.add(current)
            parent = self._hierarchy.get(current)
            if parent is None:
                break
            depth += 1
            current = parent
        return depth

    def _resolve_bounds(self, bounds_list):
        """Resolve multiple bounds to a single effective bound.

        Uses the least upper bound (most general/widest type) that
        subsumes all constraint bounds. This finds the type closest
        to the root that all bounds are subtypes of.
        """
        if not bounds_list:
            return None

        if len(bounds_list) == 1:
            return bounds_list[0]

        # Find the bound with minimum depth (closest to root = most general)
        best = bounds_list[0]
        best_depth = self._depth_of(best["bound"])

        for entry in bounds_list[1:]:
            d = self._depth_of(entry["bound"])
            if d < best_depth:
                best = entry
                best_depth = d

        return best

    def get_all_resolutions(self):
        """Return all resolved constraints across all scopes."""
        results = []
        for scope, variables in sorted(self._constraints.items()):
            for type_var, bounds_list in sorted(variables.items()):
                resolved = self._resolve_bounds(bounds_list)
                if resolved:
                    results.append({
                        "type_var": type_var,
                        "scope": scope,
                        "resolved_bound": resolved["bound"],
                        "priority": resolved["priority"],
                        "source_module": resolved["source_module"],
                    })
        return results
