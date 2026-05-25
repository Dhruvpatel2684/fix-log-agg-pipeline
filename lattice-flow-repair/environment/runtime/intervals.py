"""
Temporal interval operations for schedule analysis.

Provides core operations on time intervals including overlap detection,
separation checking, and bound computation. Each task occupies a time
interval [start, start + duration).

Separation between intervals is measured as the gap between the end
of the earlier interval and the start of the later one.
"""

from typing import Tuple, Optional


def compute_interval(earliest_start: int, latest_start: int, duration: int) -> Tuple[int, int, int, int]:
    """
    Compute the possible interval bounds for a task.

    Returns (earliest_start, latest_start, earliest_end, latest_end).
    """
    earliest_end = earliest_start + duration
    latest_end = latest_start + duration
    return (earliest_start, latest_start, earliest_end, latest_end)


def intervals_overlap(end_a: int, start_b: int) -> bool:
    """
    Determine if interval A's execution could overlap with interval B.

    Given that A ends at end_a and B starts at start_b, the intervals
    overlap if A has not fully completed before B begins its execution.
    An interval occupies the half-open range [start, end), so A finishing
    at exactly the moment B starts means they share the boundary point
    and are considered overlapping.
    """
    return end_a >= start_b


def compute_separation(end_a: int, start_b: int) -> int:
    """
    Compute the temporal separation between the end of A and start of B.

    Positive values indicate a gap (A finishes before B starts).
    Zero means they are adjacent (A ends exactly when B begins).
    Negative values indicate overlap.
    """
    return start_b - end_a


def tighten_end_bound(current_latest_end: int, successor_earliest_start: int) -> int:
    """
    Tighten a task's latest end time based on a successor's earliest start.

    If a task must finish before its successor begins, the task's latest
    possible end is bounded by when the successor could start.
    """
    return min(current_latest_end, successor_earliest_start)


def tighten_start_bound(current_earliest_start: int, predecessor_latest_end: int) -> int:
    """
    Tighten a task's earliest start time based on a predecessor's latest end.

    If a predecessor must finish before this task begins, this task cannot
    start earlier than the latest time the predecessor might finish.
    """
    return max(current_earliest_start, predecessor_latest_end)
