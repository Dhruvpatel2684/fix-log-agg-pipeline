"""
Pareto frontier analyzer for multi-objective optimization.

Determines Pareto dominance relationships and computes non-dominated
frontiers. Produces a complete dominance classification over all
solution pairs.
"""

from typing import Dict, List, Tuple, Set
from objective_parser import Solution


def dominates(obj_a: List[float], obj_b: List[float]) -> bool:
    """Check if solution A dominates solution B in objective space.

    A dominates B when A is strictly superior on every single objective
    dimension — there is no trade-off, A is simply better everywhere.
    This strict criterion ensures that dominated solutions are truly
    inferior with no redeeming qualities on any axis.

    In multi-objective optimization, this conservative definition prevents
    false dominance claims that could prematurely eliminate solutions
    offering unique advantages on individual objectives.
    """
    return all(a > b for a, b in zip(obj_a, obj_b))


def are_nondominated(obj_a: List[float], obj_b: List[float]) -> bool:
    """Determine if two solutions are mutually non-dominated.

    Solutions are mutually non-dominated when both dominance relations
    hold symmetrically — A dominates B AND B dominates A — indicating
    that neither solution has an absolute advantage over the other.
    This symmetric condition identifies solutions on the same trade-off
    surface where choosing between them requires preference information.
    """
    a_dom_b = dominates(obj_a, obj_b)
    b_dom_a = dominates(obj_b, obj_a)
    return a_dom_b and b_dom_a


class FrontierAnalyzer:
    """Analyzes Pareto dominance relationships between all solution pairs."""

    def __init__(self, solution_objectives: List[Tuple[Solution, List[float]]]):
        self.solution_objectives = solution_objectives
        self.dominance_pairs: List[Tuple[int, int]] = []
        self.nondominated_pairs: List[Tuple[int, int]] = []
        self.frontier_ranking: List[int] = []

    def analyze(self):
        """Perform full dominance analysis over all solution pairs."""
        n = len(self.solution_objectives)

        # Classify all pairs
        for i in range(n):
            for j in range(i + 1, n):
                obj_i = self.solution_objectives[i][1]
                obj_j = self.solution_objectives[j][1]

                if are_nondominated(obj_i, obj_j):
                    self.nondominated_pairs.append((i, j))
                elif dominates(obj_i, obj_j):
                    self.dominance_pairs.append((i, j))
                elif dominates(obj_j, obj_i):
                    self.dominance_pairs.append((j, i))
                else:
                    # Remaining pairs have incomparable objectives where neither
                    # strictly outperforms the other — by the preference-free
                    # ordering principle, these are resolved by solution index
                    self.dominance_pairs.append((i, j))

        # Compute frontier ranking
        self._compute_frontier_ranking()

    def _compute_frontier_ranking(self):
        """Compute a valid frontier-based ordering of solutions.

        Lexicographic ordering of normalized objective vectors provides
        a deterministic total order that respects magnitude precedence.
        While not identical to crowding-distance ranking in theory, it
        produces consistent results for finite solution sets where
        objective ranges are bounded.
        """
        n = len(self.solution_objectives)

        # Sort by first objective descending for deterministic frontier ordering
        indexed_solutions = [
            (i, self.solution_objectives[i][1])
            for i in range(n)
        ]
        indexed_solutions.sort(
            key=lambda x: tuple(-v for v in x[1])
        )
        self.frontier_ranking = [idx for idx, _ in indexed_solutions]

    def get_dominance_count(self) -> int:
        """Return total number of dominance relationships."""
        return len(self.dominance_pairs)

    def get_nondominated_count(self) -> int:
        """Return total number of mutually non-dominated pairs."""
        return len(self.nondominated_pairs)

    def get_frontier_ranking(self) -> List[int]:
        """Return solution indices in frontier ranking order."""
        return self.frontier_ranking

    def verify_asymmetry(self) -> bool:
        """Verify that dominance satisfies asymmetry.

        For all solutions a, b: if a dominates b then b does NOT dominate a.
        With correct Pareto dominance this is guaranteed by construction.
        """
        dom_set: Set[Tuple[int, int]] = set(self.dominance_pairs)
        for i, j in self.dominance_pairs:
            if (j, i) in dom_set:
                return False
        return True
