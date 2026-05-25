"""
Abstract interval domain for static program analysis.

Implements the interval abstract domain over integers, supporting
the standard lattice operations needed for fixed-point computation:
ordering, join, meet, widening, and narrowing.

The domain forms a complete lattice with:
- Bottom (empty interval): represents unreachable states
- Top (unbounded interval): represents any possible value
- Finite intervals [lo, hi]: represent bounded value ranges

Abstract interpretation computes a safe over-approximation of all
possible program behaviors by iterating transfer functions over
abstract values until reaching a post-fixed point.
"""

from typing import Optional, Tuple, List, Set

# Sentinel values for unbounded intervals
NEG_INF = float('-inf')
POS_INF = float('inf')


class Interval:
    """Represents an abstract interval [lo, hi] or bottom (empty)."""

    __slots__ = ('lo', 'hi', '_is_bottom')

    def __init__(self, lo=None, hi=None, bottom=False):
        if bottom:
            self.lo = None
            self.hi = None
            self._is_bottom = True
        else:
            self.lo = lo if lo is not None else NEG_INF
            self.hi = hi if hi is not None else POS_INF
            self._is_bottom = False

    @staticmethod
    def bottom():
        """Create the bottom element (empty set / unreachable)."""
        return Interval(bottom=True)

    @staticmethod
    def top():
        """Create the top element (all integers)."""
        return Interval(NEG_INF, POS_INF)

    @staticmethod
    def const(value: int):
        """Create a singleton interval [v, v]."""
        return Interval(value, value)

    @property
    def is_bottom(self) -> bool:
        return self._is_bottom

    @property
    def is_top(self) -> bool:
        return not self._is_bottom and self.lo == NEG_INF and self.hi == POS_INF

    def contains(self, value: int) -> bool:
        """Check if a concrete value is within this interval."""
        if self._is_bottom:
            return False
        return self.lo <= value <= self.hi

    def is_subset_of(self, other: 'Interval') -> bool:
        """Check if this interval is a subset of (less than or equal to) other.

        In the interval lattice, [a,b] ⊑ [c,d] iff c <= a and b <= d.
        Bottom is below everything. Top is above everything.
        """
        if self._is_bottom:
            return True
        if other._is_bottom:
            return False
        if other.lo == NEG_INF and other.hi == POS_INF:
            return True
        return other.lo <= self.lo and self.hi <= other.hi

    def __eq__(self, other):
        if not isinstance(other, Interval):
            return NotImplemented
        if self._is_bottom and other._is_bottom:
            return True
        if self._is_bottom or other._is_bottom:
            return False
        return self.lo == other.lo and self.hi == other.hi

    def __repr__(self):
        if self._is_bottom:
            return "⊥"
        if self.is_top:
            return "⊤"
        lo_s = "-∞" if self.lo == NEG_INF else str(self.lo)
        hi_s = "+∞" if self.hi == POS_INF else str(self.hi)
        return f"[{lo_s}, {hi_s}]"

    def to_dict(self):
        """Serialize to JSON-compatible dict."""
        if self._is_bottom:
            return {"type": "bottom"}
        return {
            "type": "interval",
            "lo": None if self.lo == NEG_INF else self.lo,
            "hi": None if self.hi == POS_INF else self.hi
        }


def interval_join(a: Interval, b: Interval) -> Interval:
    """
    Compute the join (least upper bound) of two intervals.

    The join of two intervals is the smallest interval containing both.
    This is used at control-flow merge points where execution could
    have followed either branch — the result must account for values
    from both paths.

    join([a,b], [c,d]) = [min(a,c), max(b,d)]
    join(⊥, x) = x
    join(x, ⊥) = x
    """
    if a.is_bottom:
        return b
    if b.is_bottom:
        return a
    return Interval(min(a.lo, b.lo), max(a.hi, b.hi))


def interval_meet(a: Interval, b: Interval) -> Interval:
    """
    Compute the meet (greatest lower bound) of two intervals.

    The meet of two intervals is their intersection — the largest
    interval contained in both. This represents values that MUST
    satisfy both constraints simultaneously.

    meet([a,b], [c,d]) = [max(a,c), min(b,d)] if non-empty, else ⊥
    meet(⊥, x) = ⊥
    meet(x, ⊥) = ⊥
    """
    if a.is_bottom or b.is_bottom:
        return Interval.bottom()
    new_lo = max(a.lo, b.lo)
    new_hi = min(a.hi, b.hi)
    if new_lo > new_hi:
        return Interval.bottom()
    return Interval(new_lo, new_hi)


def interval_widen(old: Interval, new: Interval) -> Interval:
    """
    Apply widening to accelerate convergence to a fixed point.

    Widening ensures termination of the abstract iteration by
    extrapolating bounds that are still changing. When the new
    iterate exceeds the old bound in some direction, that bound
    is pushed to infinity.

    The widening operator compares the previous iterate (old) with
    the current iterate (new) and produces a result that is
    guaranteed to stabilize within finitely many steps.

    Standard widening:
      - If new.lo < old.lo: result.lo = -∞ (lower bound still decreasing)
      - Otherwise: result.lo = old.lo (lower bound has stabilized)
      - If new.hi > old.hi: result.hi = +∞ (upper bound still increasing)
      - Otherwise: result.hi = old.hi (upper bound has stabilized)
    """
    if old.is_bottom:
        return new
    if new.is_bottom:
        return old

    # Compare new iterate against old to determine stability
    widen_lo = NEG_INF if new.lo < old.lo else new.lo
    widen_hi = POS_INF if new.hi > old.hi else new.hi

    return Interval(widen_lo, widen_hi)


def interval_narrow(old: Interval, new: Interval) -> Interval:
    """
    Apply narrowing to refine an over-approximation.

    After widening produces a post-fixed point (which may be too coarse),
    narrowing refines it by tightening bounds that were pushed to infinity
    during widening, using the information from a new iterate that may
    have tighter finite bounds.

    Narrowing replaces infinite bounds with finite ones when available.
    """
    if old.is_bottom:
        return Interval.bottom()
    if new.is_bottom:
        return old

    narrow_lo = new.lo if old.lo == NEG_INF else old.lo
    narrow_hi = new.hi if old.hi == POS_INF else old.hi

    return Interval(narrow_lo, narrow_hi)


def transfer_add(a: Interval, b: Interval) -> Interval:
    """Transfer function for addition: [a,b] + [c,d] = [a+c, b+d]."""
    if a.is_bottom or b.is_bottom:
        return Interval.bottom()
    lo = NEG_INF if (a.lo == NEG_INF or b.lo == NEG_INF) else a.lo + b.lo
    hi = POS_INF if (a.hi == POS_INF or b.hi == POS_INF) else a.hi + b.hi
    return Interval(lo, hi)


def transfer_sub(a: Interval, b: Interval) -> Interval:
    """Transfer function for subtraction: [a,b] - [c,d] = [a-d, b-c]."""
    if a.is_bottom or b.is_bottom:
        return Interval.bottom()
    lo = NEG_INF if (a.lo == NEG_INF or b.hi == POS_INF) else a.lo - b.hi
    hi = POS_INF if (a.hi == POS_INF or b.lo == NEG_INF) else a.hi - b.lo
    return Interval(lo, hi)


def transfer_mul(a: Interval, b: Interval) -> Interval:
    """Transfer function for multiplication."""
    if a.is_bottom or b.is_bottom:
        return Interval.bottom()
    if a.lo == NEG_INF or a.hi == POS_INF or b.lo == NEG_INF or b.hi == POS_INF:
        return Interval.top()
    products = [a.lo * b.lo, a.lo * b.hi, a.hi * b.lo, a.hi * b.hi]
    return Interval(min(products), max(products))


def merge_states(states: List[Interval]) -> Interval:
    """
    Merge abstract values from multiple incoming control flow paths.

    At a program point with multiple predecessors (e.g., after an
    if-else or at a loop header), the abstract value must account
    for all possible concrete values that could arrive from any
    predecessor path.

    For a sound analysis, the merged value is the combination that
    reflects the constraints imposed by all incoming paths — the
    strongest statement we can make about values at the merge point
    given that execution arrived from one of the predecessor paths.
    """
    result = Interval.bottom()
    for state in states:
        if state.is_bottom:
            continue
        if result.is_bottom:
            result = state
            continue
        # Combine: tightest interval consistent with all predecessors
        new_lo = max(result.lo, state.lo)
        new_hi = min(result.hi, state.hi)
        if new_lo > new_hi:
            result = Interval.bottom()
        else:
            result = Interval(new_lo, new_hi)
    return result
