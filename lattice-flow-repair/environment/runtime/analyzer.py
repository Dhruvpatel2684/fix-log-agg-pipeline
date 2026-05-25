"""
Fixed-point analyzer for abstract interpretation over program traces.

Computes the abstract semantics of program traces by iterating
transfer functions over the interval domain until reaching a
post-fixed point. Uses widening to guarantee termination and
narrowing to refine the result.

The analysis processes structured traces that represent simplified
program control flow with assignments, conditionals, and loops.
"""

import configparser
from typing import Dict, List, Any, Tuple
from runtime.domain import (
    Interval, interval_join, interval_meet, interval_widen,
    interval_narrow, transfer_add, transfer_sub, transfer_mul,
    merge_states, NEG_INF, POS_INF
)


class TraceAnalyzer:
    """Analyzes program traces using abstract interpretation."""

    def __init__(self, config_path: str):
        config = configparser.ConfigParser()
        config.read(config_path)
        self._widening_delay = config.getint("analysis", "widening_delay")
        self._max_iterations = config.getint("analysis", "max_iterations")

    def analyze_trace(self, trace: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a single program trace and return abstract results.

        Processes the trace instructions, computing abstract interval
        values for all variables at each program point.
        """
        variables = trace.get("initial_vars", {})
        instructions = trace.get("instructions", [])
        loops = trace.get("loops", [])

        # Initialize abstract state
        state: Dict[str, Interval] = {}
        for var, init in variables.items():
            if isinstance(init, dict):
                lo = init.get("lo", NEG_INF)
                hi = init.get("hi", POS_INF)
                state[var] = Interval(lo, hi)
            elif isinstance(init, int):
                state[var] = Interval.const(init)
            else:
                state[var] = Interval.top()

        # Process sequential instructions
        state = self._process_block(state, instructions)

        # Process loops to fixed point
        for loop in loops:
            state = self._analyze_loop(state, loop)

        # Convert results
        result = {}
        for var, interval in state.items():
            result[var] = interval.to_dict()

        return result

    def _process_block(
        self, state: Dict[str, Interval], instructions: List[Dict]
    ) -> Dict[str, Interval]:
        """Process a basic block of instructions sequentially."""
        for instr in instructions:
            state = self._apply_instruction(state, instr)
        return state

    def _apply_instruction(
        self, state: Dict[str, Interval], instr: Dict
    ) -> Dict[str, Interval]:
        """Apply a single instruction to the abstract state."""
        op = instr["op"]

        if op == "assign":
            target = instr["target"]
            value = self._eval_expr(state, instr["value"])
            state[target] = value

        elif op == "add":
            target = instr["target"]
            left = self._get_var(state, instr["left"])
            right = self._get_var(state, instr["right"])
            state[target] = transfer_add(left, right)

        elif op == "sub":
            target = instr["target"]
            left = self._get_var(state, instr["left"])
            right = self._get_var(state, instr["right"])
            state[target] = transfer_sub(left, right)

        elif op == "mul":
            target = instr["target"]
            left = self._get_var(state, instr["left"])
            right = self._get_var(state, instr["right"])
            state[target] = transfer_mul(left, right)

        elif op == "branch":
            # Process both branches and merge results
            then_state = self._process_block(
                dict(state), instr.get("then_block", [])
            )
            else_state = self._process_block(
                dict(state), instr.get("else_block", [])
            )
            state = self._merge_branch_states(then_state, else_state)

        return state

    def _merge_branch_states(
        self, state_a: Dict[str, Interval], state_b: Dict[str, Interval]
    ) -> Dict[str, Interval]:
        """
        Merge two abstract states from divergent control flow paths.

        After a conditional branch, the abstract state must reflect
        all possible values from either path. Each variable's abstract
        value is the combination of its values from both branches.
        """
        all_vars = set(state_a.keys()) | set(state_b.keys())
        merged = {}
        for var in all_vars:
            val_a = state_a.get(var, Interval.bottom())
            val_b = state_b.get(var, Interval.bottom())
            merged[var] = merge_states([val_a, val_b])
        return merged

    def _analyze_loop(
        self, entry_state: Dict[str, Interval], loop: Dict
    ) -> Dict[str, Interval]:
        """
        Analyze a loop to compute its abstract fixed point.

        Uses Kleene iteration with widening to ensure termination:
        1. Start with the entry state
        2. Apply the loop body transfer function
        3. Merge the loop-back edge with the entry
        4. Apply widening after the configured delay
        5. Repeat until stable

        After widening produces a post-fixed point, optionally apply
        narrowing iterations to refine.
        """
        body = loop.get("body", [])
        loop_vars = loop.get("modified_vars", list(entry_state.keys()))
        narrowing_passes = loop.get("narrowing_passes", 2)

        # Initialize loop state from entry
        loop_state = dict(entry_state)
        prev_state = {var: Interval.bottom() for var in loop_vars}

        iteration = 0
        converged = False

        # Ascending (widening) phase
        while iteration < self._max_iterations and not converged:
            iteration += 1

            # Apply loop body
            new_state = self._process_block(dict(loop_state), body)

            # Merge back edge with entry state for loop header
            # At loop headers, the incoming value is the join of the
            # entry value (first iteration) and the back-edge value
            header_state = {}
            for var in loop_vars:
                entry_val = entry_state.get(var, Interval.bottom())
                back_val = new_state.get(var, Interval.bottom())
                header_state[var] = interval_join(entry_val, back_val)

            # Apply widening after delay
            if iteration > self._widening_delay:
                for var in loop_vars:
                    header_state[var] = interval_widen(
                        loop_state.get(var, Interval.bottom()),
                        header_state[var]
                    )

            # Check convergence
            converged = all(
                header_state.get(var, Interval.bottom()) ==
                loop_state.get(var, Interval.bottom())
                for var in loop_vars
            )

            # Update loop state
            for var in loop_vars:
                loop_state[var] = header_state[var]

        # Descending (narrowing) phase to refine over-approximation
        for _ in range(narrowing_passes):
            new_state = self._process_block(dict(loop_state), body)
            for var in loop_vars:
                entry_val = entry_state.get(var, Interval.bottom())
                back_val = new_state.get(var, Interval.bottom())
                refined = interval_join(entry_val, back_val)
                loop_state[var] = interval_narrow(loop_state[var], refined)

        # Preserve non-loop variables from entry
        for var in entry_state:
            if var not in loop_vars:
                loop_state[var] = entry_state[var]

        return loop_state

    def _eval_expr(self, state: Dict[str, Interval], expr) -> Interval:
        """Evaluate an expression to an abstract interval."""
        if isinstance(expr, int):
            return Interval.const(expr)
        if isinstance(expr, str):
            return self._get_var(state, expr)
        if isinstance(expr, dict):
            if "lo" in expr and "hi" in expr:
                return Interval(expr["lo"], expr["hi"])
            if "var" in expr:
                return self._get_var(state, expr["var"])
        return Interval.top()

    def _get_var(self, state: Dict[str, Interval], name: str) -> Interval:
        """Get a variable's abstract value, or top if undefined."""
        if isinstance(name, int):
            return Interval.const(name)
        if isinstance(name, dict):
            return Interval(name.get("lo", NEG_INF), name.get("hi", POS_INF))
        return state.get(name, Interval.top())
