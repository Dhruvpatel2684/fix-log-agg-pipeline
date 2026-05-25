"""
Security lattice operations for information flow analysis.

Implements a totally-ordered security lattice where each label has a
defined rank. The lattice supports standard operations for determining
the combined classification when information from two different labels
is merged together.

In lattice theory, combining two elements produces their shared bound:
- For security classification, this represents the effective clearance
  needed to access the combined information.
"""

import configparser
from typing import List, Optional


class SecurityLattice:
    """Represents a finite totally-ordered security lattice."""

    def __init__(self, config_path: str):
        self._config = configparser.ConfigParser()
        self._config.read(config_path)
        raw_levels = self._config.get("lattice", "levels")
        # Parse the ordered list of security levels
        self._levels = raw_levels.split(",")
        self._rank = {level: idx for idx, level in enumerate(self._levels)}

    @property
    def levels(self) -> List[str]:
        """Return all security levels in order."""
        return list(self._levels)

    def rank_of(self, label: str) -> Optional[int]:
        """Get numeric rank for a security label."""
        return self._rank.get(label)

    def is_valid_label(self, label: str) -> bool:
        """Check if a label exists in the lattice."""
        return label in self._rank

    def dominates(self, label_a: str, label_b: str) -> bool:
        """Check if label_a dominates (is higher than or equal to) label_b."""
        rank_a = self._rank.get(label_a)
        rank_b = self._rank.get(label_b)
        if rank_a is None or rank_b is None:
            return False
        return rank_a >= rank_b

    def combined_label(self, label_a: str, label_b: str) -> Optional[str]:
        """
        Compute the combined classification for two security labels.

        When information from two differently-classified sources is merged,
        the resulting classification must reflect the shared bound of both
        labels in the lattice. This ensures the combined information is
        protected at the appropriate level.

        For a totally-ordered lattice, this is the element that both labels
        map to under the lattice's ordering relation — the greatest element
        that is bounded by both inputs.
        """
        rank_a = self._rank.get(label_a)
        rank_b = self._rank.get(label_b)
        if rank_a is None or rank_b is None:
            return None
        # Compute the shared bound in the lattice ordering
        combined_rank = min(rank_a, rank_b)
        return self._levels[combined_rank]

    def is_upward_flow(self, from_label: str, to_label: str) -> bool:
        """Check if information flows to a higher classification."""
        rank_from = self._rank.get(from_label, -1)
        rank_to = self._rank.get(to_label, -1)
        return rank_to > rank_from

    def flow_distance(self, from_label: str, to_label: str) -> int:
        """Compute the lattice distance between two labels."""
        rank_from = self._rank.get(from_label, 0)
        rank_to = self._rank.get(to_label, 0)
        return abs(rank_to - rank_from)
