"""
CUBIC Congestion Control State Machine

Implements TCP CUBIC (RFC 8312) congestion window management including
slow-start, congestion avoidance with cubic growth, and fast recovery.

CUBIC uses a cubic function for window growth during congestion avoidance,
providing better scalability for high-bandwidth long-delay networks compared
to traditional linear growth (Reno).

The cubic window function is:
    W(t) = C * (t - K)^3 + W_max

where:
    C     = CUBIC scaling constant
    t     = time since last congestion event
    K     = time period to reach W_max under cubic growth
    W_max = window size just before last reduction

States:
    SLOW_START        - Exponential growth until ssthresh
    CONGESTION_AVOID  - Cubic growth function
    FAST_RECOVERY     - Window reduction and retransmission

References:
    RFC 8312 - CUBIC for Fast and Long-Distance Networks
    RFC 5681 - TCP Congestion Control
"""

import math
from typing import Dict, Optional, List, Tuple
from enum import Enum


class CongestionState(Enum):
    """TCP congestion control state enumeration."""
    SLOW_START = "slow_start"
    CONGESTION_AVOIDANCE = "congestion_avoidance"
    FAST_RECOVERY = "fast_recovery"


class WindowTracker:
    """
    Tracks congestion window history for analysis and reporting.
    
    Maintains a bounded history of window size changes with timestamps
    for post-hoc analysis of congestion control dynamics.
    """

    def __init__(self, max_history: int = 2000):
        """
        Initialize window tracker.
        
        Args:
            max_history: Maximum number of window events to retain
        """
        self._history: List[Tuple[float, float, str]] = []
        self._max_history = max_history
        self._state_transitions: List[Tuple[float, str, str]] = []
        self._loss_events: List[Tuple[float, float]] = []
        self._max_window_seen = 0.0
        self._min_window_seen = float('inf')

    def record_window(self, timestamp_ms: float, cwnd: float, state: str):
        """Record a window size observation."""
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append((timestamp_ms, cwnd, state))
        self._max_window_seen = max(self._max_window_seen, cwnd)
        if cwnd > 0:
            self._min_window_seen = min(self._min_window_seen, cwnd)

    def record_state_change(self, timestamp_ms: float, 
                            from_state: str, to_state: str):
        """Record a state transition event."""
        self._state_transitions.append((timestamp_ms, from_state, to_state))

    def record_loss(self, timestamp_ms: float, cwnd_at_loss: float):
        """Record a loss event with window size at time of loss."""
        self._loss_events.append((timestamp_ms, cwnd_at_loss))

    @property
    def history(self) -> List[Tuple[float, float, str]]:
        """Full window history as (time, cwnd, state) tuples."""
        return self._history

    @property
    def loss_events(self) -> List[Tuple[float, float]]:
        """All recorded loss events."""
        return self._loss_events

    @property
    def max_window(self) -> float:
        """Maximum window size observed."""
        return self._max_window_seen

    def get_average_window(self) -> float:
        """Compute average window size over history."""
        if not self._history:
            return 0.0
        return sum(w for _, w, _ in self._history) / len(self._history)


class CUBICController:
    """
    TCP CUBIC congestion control implementation.
    
    Manages the congestion window through slow-start, CUBIC congestion
    avoidance, and fast recovery phases. The controller responds to ACK
    and loss events to regulate sending rate.
    
    The CUBIC function provides:
    - Aggressive probing far from W_max (convex region)
    - Cautious probing near W_max (concave region)  
    - Window-independent growth rate (fairness in diverse RTTs)
    """

    def __init__(self, config: Dict):
        """
        Initialize CUBIC controller from configuration.
        
        Args:
            config: Dictionary with CUBIC parameters:
                - C: CUBIC scaling constant (default 0.4)
                - beta: Multiplicative decrease factor (default 0.7)
                - initial_cwnd: Initial window in segments (default 10)
        """
        self._C = config.get("C", 0.4)
        self._beta = config.get("beta", 0.7)
        self._initial_cwnd = config.get("initial_cwnd", 10)
        
        # Congestion window state
        self._cwnd = float(self._initial_cwnd)
        self._ssthresh = float('inf')  # Start with no threshold
        self._state = CongestionState.SLOW_START
        
        # CUBIC epoch tracking
        self._epoch_start: float = 0.0
        self._w_max: float = 0.0
        self._K: float = 0.0
        self._origin_point: float = 0.0
        
        # ACK counting for window growth
        self._ack_count: int = 0
        self._bytes_acked_this_round: int = 0
        self._last_round_trip: float = 0.0
        
        # Recovery state
        self._recovery_start_seq: int = 0
        self._in_recovery: bool = False
        self._recovery_cwnd: float = 0.0
        
        # Hystart for slow-start exit
        self._round_start_time: float = 0.0
        self._round_min_rtt: float = float('inf')
        self._last_round_min_rtt: float = float('inf')
        self._consecutive_rtt_increases: int = 0
        
        # Tracker for history
        self._tracker = WindowTracker()
        self._total_acks = 0
        self._total_losses = 0

    def on_ack(self, timestamp_ms: float, bytes_acked: int,
               rtt_ms: float, min_rtt_ms: float) -> float:
        """
        Process an ACK event and update congestion window.
        
        Advances the window according to the current state:
        - SLOW_START: exponential increase (double per RTT)
        - CONGESTION_AVOIDANCE: CUBIC function growth
        - FAST_RECOVERY: limited increase during recovery
        
        Args:
            timestamp_ms: ACK arrival time in milliseconds
            bytes_acked: Number of bytes acknowledged
            rtt_ms: RTT measurement from this ACK
            min_rtt_ms: Current minimum RTT estimate
            
        Returns:
            Updated congestion window in segments
        """
        self._total_acks += 1
        self._ack_count += 1
        self._bytes_acked_this_round += bytes_acked

        # Track per-round RTT for HyStart
        self._round_min_rtt = min(self._round_min_rtt, rtt_ms)

        if self._state == CongestionState.SLOW_START:
            self._slow_start_update(timestamp_ms, bytes_acked, rtt_ms)
        elif self._state == CongestionState.CONGESTION_AVOIDANCE:
            self._cubic_update(timestamp_ms, rtt_ms, min_rtt_ms)
        elif self._state == CongestionState.FAST_RECOVERY:
            # In recovery, inflate window by one segment per ACK
            self._cwnd += 1.0

        # Record window state
        self._tracker.record_window(timestamp_ms, self._cwnd, self._state.value)

        return self._cwnd

    def on_loss(self, timestamp_ms: float, lost_seq: int) -> float:
        """
        Handle a packet loss event.
        
        Reduces the congestion window by the multiplicative decrease factor
        (beta) and enters either fast recovery or updates CUBIC state.
        
        Args:
            timestamp_ms: Time loss was detected
            lost_seq: Sequence number of lost packet
            
        Returns:
            Updated congestion window after reduction
        """
        self._total_losses += 1
        self._tracker.record_loss(timestamp_ms, self._cwnd)

        if self._in_recovery:
            # Already in recovery, don't reduce again
            return self._cwnd

        # Save W_max for CUBIC computation
        self._w_max = self._cwnd

        # On congestion: ssthresh set to current window for
        # subsequent slow-start exit threshold
        self._ssthresh = self._cwnd

        # Reduce window by beta factor
        self._cwnd = max(int(self._cwnd * self._beta), 2)
        
        # Reset CUBIC epoch
        self._epoch_start = timestamp_ms
        
        # Time to reach W_max from reduced window under cubic growth
        # K = cbrt(W_max / C) using the full pre-reduction window
        self._K = (self._w_max / self._C) ** (1.0 / 3.0)
        
        self._origin_point = self._w_max

        # Enter recovery
        old_state = self._state
        self._state = CongestionState.FAST_RECOVERY
        self._in_recovery = True
        self._recovery_start_seq = lost_seq
        self._recovery_cwnd = self._cwnd
        
        self._tracker.record_state_change(
            timestamp_ms, old_state.value, self._state.value
        )

        return self._cwnd

    def on_recovery_complete(self, timestamp_ms: float) -> float:
        """
        Exit fast recovery and enter congestion avoidance.
        
        Called when all packets outstanding at the time of loss
        have been acknowledged, indicating recovery is complete.
        
        Args:
            timestamp_ms: Time recovery completed
            
        Returns:
            Window size entering congestion avoidance
        """
        self._in_recovery = False
        old_state = self._state
        self._state = CongestionState.CONGESTION_AVOIDANCE
        
        # Set window to the recovery target (ssthresh)
        self._cwnd = self._ssthresh if self._ssthresh < float('inf') else self._cwnd
        
        # Reset epoch for fresh CUBIC computation
        self._epoch_start = timestamp_ms
        self._ack_count = 0
        
        self._tracker.record_state_change(
            timestamp_ms, old_state.value, self._state.value
        )

        return self._cwnd

    def _slow_start_update(self, timestamp_ms: float, 
                            bytes_acked: int, rtt_ms: float):
        """
        Exponential window growth during slow-start.
        
        Increases cwnd by one segment for each ACK received (effectively
        doubling per RTT). Exits to congestion avoidance when ssthresh
        is reached or HyStart detects delay increase.
        """
        # Standard slow-start: increase by 1 MSS per ACK
        self._cwnd += 1.0

        # Check for ssthresh exit
        if self._cwnd >= self._ssthresh:
            old_state = self._state
            self._state = CongestionState.CONGESTION_AVOIDANCE
            self._epoch_start = timestamp_ms
            self._tracker.record_state_change(
                timestamp_ms, old_state.value, self._state.value
            )

    def _cubic_update(self, timestamp_ms: float, 
                      rtt_ms: float, min_rtt_ms: float):
        """
        CUBIC congestion avoidance window growth.
        
        Computes target window using the cubic function:
            W(t) = C * (t - K)^3 + W_max
        
        The window is increased toward the CUBIC target at most once
        per RTT to maintain TCP-friendliness.
        """
        if self._epoch_start == 0:
            self._epoch_start = timestamp_ms
            self._ack_count = 0
            return

        # Compute elapsed time since epoch start
        elapsed_sec = (timestamp_ms - self._epoch_start) / 1000.0

        # CUBIC target window
        # W(t) = C * (t - K)^3 + W_max
        w_cubic = self._C * (elapsed_sec - self._K) ** 3 + self._w_max

        # TCP-friendly estimate (Reno-equivalent growth)
        # W_est grows linearly: 3*beta/(2-beta) per RTT
        rtt_sec = max(rtt_ms / 1000.0, 0.001)
        w_est = self._w_max * self._beta + \
                (3.0 * (1.0 - self._beta) / (1.0 + self._beta)) * \
                (elapsed_sec / rtt_sec)

        # Use maximum of cubic and TCP-friendly (ensures fairness)
        w_target = max(w_cubic, w_est)

        # Adjust window toward target, at most 1 segment per ACK
        if w_target > self._cwnd:
            increase = min((w_target - self._cwnd) / self._cwnd, 1.0)
            self._cwnd += increase
        elif w_target < self._cwnd:
            # CUBIC can decrease above W_max in concave region
            pass  # Don't decrease during congestion avoidance

    @property
    def cwnd(self) -> float:
        """Current congestion window in segments."""
        return self._cwnd

    @property
    def ssthresh(self) -> float:
        """Current slow-start threshold."""
        return self._ssthresh

    @property
    def state(self) -> CongestionState:
        """Current congestion control state."""
        return self._state

    @property
    def w_max(self) -> float:
        """Window size before last reduction."""
        return self._w_max

    @property
    def tracker(self) -> WindowTracker:
        """Access window history tracker."""
        return self._tracker

    def get_state_summary(self) -> Dict:
        """Get comprehensive state summary for reporting."""
        return {
            "cwnd": self._cwnd,
            "ssthresh": self._ssthresh if self._ssthresh < float('inf') else -1,
            "state": self._state.value,
            "w_max": self._w_max,
            "K": self._K,
            "total_acks": self._total_acks,
            "total_losses": self._total_losses,
            "in_recovery": self._in_recovery,
            "avg_window": self._tracker.get_average_window()
        }
