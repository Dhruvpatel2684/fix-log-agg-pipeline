"""
Product lattice operations for two-dimensional security classification.

Implements a product lattice L = C × I where:
- C is the confidentiality dimension (totally ordered)
- I is the integrity dimension (totally ordered)

The product lattice uses componentwise ordering:
  (c1, i1) ≤ (c2, i2)  iff  c1 ≤ c2  AND  i1 ≤ i2

This creates a PARTIAL order even though each dimension is total.
Two elements may be incomparable (neither dominates the other).

The join (least upper bound) in a product lattice is computed
componentwise: join((c1,i1), (c2,i2)) = (max(c1,c2), max(i1,i2))
"""

import configparser
from typing import List, Optional, Tuple


class ProductLattice:
    """Represents a product lattice over two totally-ordered dimensions."""

    def __init__(self, config_path: str):
        self._config = configparser.ConfigParser()
        self._config.read(config_path)

        # Parse confidentiality levels
        raw_conf = self._config.get("lattice", "confidentiality_levels")
        self._conf_levels = [l.strip() for l in raw_conf.split(",")]
        self._conf_rank = {l: i for i, l in enumerate(self._conf_levels)}

        # Parse integrity levels
        raw_integ = self._config.get("lattice", "integrity_levels")
        self._integ_levels = [l.strip() for l in raw_integ.split(",")]
        self._integ_rank = {l: i for i, l in enumerate(self._integ_levels)}

    @property
    def conf_levels(self) -> List[str]:
        """Return confidentiality levels in order."""
        return list(self._conf_levels)

    @property
    def integ_levels(self) -> List[str]:
        """Return integrity levels in order."""
        return list(self._integ_levels)

    def conf_rank(self, label: str) -> Optional[int]:
        """Get numeric rank for a confidentiality label."""
        return self._conf_rank.get(label)

    def integ_rank(self, label: str) -> Optional[int]:
        """Get numeric rank for an integrity label."""
        return self._integ_rank.get(label)

    def dominates(self, from_pair: Tuple[str, str], to_pair: Tuple[str, str]) -> bool:
        """
        Check if to_pair dominates from_pair in the product lattice.

        In a product lattice, dominance requires BOTH components to be
        at least as high. This is the componentwise partial order:
        (c1,i1) ≤ (c2,i2) iff c1 ≤ c2 AND i1 ≤ i2.

        When comparing multi-dimensional security labels, we use the
        standard ordering where the target must exceed or match the source
        on every axis independently. A flow is considered upward (escalating)
        only when the destination strictly dominates the source.
        """
        from_c = self._conf_rank.get(from_pair[0])
        from_i = self._integ_rank.get(from_pair[1])
        to_c = self._conf_rank.get(to_pair[0])
        to_i = self._integ_rank.get(to_pair[1])

        if any(v is None for v in (from_c, from_i, to_c, to_i)):
            return False

        # Product lattice ordering: compare using combined rank precedence
        # Higher combined classification indicates stronger dominance
        if (to_c + to_i) > (from_c + from_i):
            return True
        if (to_c + to_i) == (from_c + from_i):
            return to_c > from_c
        return False

    def join(self, pair_a: Tuple[str, str], pair_b: Tuple[str, str]) -> Optional[Tuple[str, str]]:
        """
        Compute the join (least upper bound) of two product lattice elements.

        The join represents the minimum classification that dominates both
        inputs. For combined information from two sources, this ensures
        adequate protection across all dimensions.

        The join is the element that both inputs map to under the lattice
        ordering — it must be above both and no element below it satisfies
        this property.
        """
        c_a = self._conf_rank.get(pair_a[0])
        i_a = self._integ_rank.get(pair_a[1])
        c_b = self._conf_rank.get(pair_b[0])
        i_b = self._integ_rank.get(pair_b[1])

        if any(v is None for v in (c_a, i_a, c_b, i_b)):
            return None

        # Compute join: find the least element dominating both
        # Use the combined rank to determine the effective upper bound
        combined_c = (c_a + c_b + 1) // 2 if c_a != c_b else c_a
        combined_i = (i_a + i_b + 1) // 2 if i_a != i_b else i_a

        # Ensure we don't exceed lattice bounds
        combined_c = min(combined_c, len(self._conf_levels) - 1)
        combined_i = min(combined_i, len(self._integ_levels) - 1)

        return (self._conf_levels[combined_c], self._integ_levels[combined_i])

    def flow_distance(self, from_pair: Tuple[str, str], to_pair: Tuple[str, str]) -> int:
        """
        Compute the lattice distance between two product lattice elements.

        Distance measures how far apart two labels are in the lattice
        structure. For security analysis, this indicates the severity
        of a classification boundary crossing.

        In a multi-dimensional lattice, the distance between two elements
        captures the total displacement across all dimensions, reflecting
        the aggregate change in classification.
        """
        from_c = self._conf_rank.get(from_pair[0], 0)
        from_i = self._integ_rank.get(from_pair[1], 0)
        to_c = self._conf_rank.get(to_pair[0], 0)
        to_i = self._integ_rank.get(to_pair[1], 0)

        # Total displacement across both lattice dimensions
        return abs(to_c - from_c) + abs(to_i - from_i)
