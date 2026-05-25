"""
Constraint propagation engine for temporal scheduling.

Implements iterative bound tightening: given ordering constraints
between tasks, propagates timing restrictions to narrow the feasible
windows for each task. The propagation continues for a configured
number of passes to propagate indirect constraints.

After propagation, a schedule is feasible if every task's tightened
window still admits at least one valid start time (earliest <= latest).
"""

import configparser
from typing import Dict, Any, List, Tuple
from runtime.intervals import tighten_end_bound, tighten_start_bound


class ConstraintPropagator:
    """Propagates temporal ordering constraints to tighten task bounds."""

    def __init__(self, config_path: str):
        self._config = configparser.ConfigParser()
        self._config.read(config_path)
        self._max_passes = self._config.getint("scheduler", "max_propagation_passes")

    def propagate(
        self,
        tasks: Dict[str, Dict[str, int]],
        constraints: List[Dict[str, str]]
    ) -> Dict[str, Dict[str, int]]:
        """
        Propagate constraints to tighten task timing bounds.

        For each 'before' constraint (A before B):
        - A's latest end is bounded by B's earliest start
        - B's earliest start is bounded by A's latest end

        Returns the tightened task bounds after propagation.
        """
        # Initialize working bounds
        bounds = {}
        for name, task in tasks.items():
            bounds[name] = {
                "earliest_start": task["earliest_start"],
                "latest_start": task["latest_start"],
                "duration": task["duration"],
                "earliest_end": task["earliest_start"] + task["duration"],
                "latest_end": task["latest_start"] + task["duration"]
            }

        # Propagate for configured number of passes
        for _ in range(self._max_passes):
            for constraint in constraints:
                if constraint["type"] == "before":
                    pred = constraint["from"]
                    succ = constraint["to"]

                    # Tighten predecessor's latest end
                    new_latest_end = tighten_end_bound(
                        bounds[pred]["latest_end"],
                        bounds[succ]["earliest_start"]
                    )
                    if new_latest_end < bounds[pred]["latest_end"]:
                        bounds[pred]["latest_end"] = new_latest_end
                        bounds[pred]["latest_start"] = new_latest_end - bounds[pred]["duration"]

                    # Tighten successor's earliest start
                    new_earliest_start = tighten_start_bound(
                        bounds[succ]["earliest_start"],
                        bounds[pred]["latest_end"]
                    )
                    if new_earliest_start > bounds[succ]["earliest_start"]:
                        bounds[succ]["earliest_start"] = new_earliest_start
                        bounds[succ]["earliest_end"] = new_earliest_start + bounds[succ]["duration"]

        return bounds

    def check_feasibility(self, bounds: Dict[str, Dict[str, int]]) -> Tuple[bool, List[str]]:
        """
        Check if the propagated bounds admit a feasible schedule.

        A schedule is infeasible if any task's earliest_start exceeds
        its latest_start (empty window).
        """
        infeasible_tasks = []
        for name, b in bounds.items():
            if b["earliest_start"] > b["latest_start"]:
                infeasible_tasks.append(name)

        return (len(infeasible_tasks) == 0, infeasible_tasks)
