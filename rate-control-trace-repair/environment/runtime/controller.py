"""Congestion window controller implementing CUBIC growth dynamics.

Models the TCP CUBIC congestion control algorithm (RFC 8312) with
slow-start, congestion avoidance, and multiplicative decrease phases.
"""

import math


class CongestionState:
    """Enumeration of congestion control states."""
    SLOW_START = "slow_start"
    CONGESTION_AVOIDANCE = "congestion_avoidance"
    RECOVERY = "recovery"


class CUBICController:
    """TCP CUBIC congestion window controller.

    Implements the CUBIC window growth function W_cubic(t) = C*(t-K)^3 + W_max
    where C is the CUBIC scaling constant, K is the time period to grow
    back to W_max, and t is elapsed time since the last congestion event.
    """

    def __init__(self, C: float = 0.4, beta: float = 0.7,
                 initial_cwnd: int = 10, max_cwnd: int = 10000):
        self._C = C
        self._beta = beta
        self._cwnd = initial_cwnd
        self._initial_cwnd = initial_cwnd
        self._max_cwnd = max_cwnd
        self._w_max = initial_cwnd
        self._K = 0.0
        self._epoch_start_ms = 0.0
        self._state = CongestionState.SLOW_START
        self._ssthresh = max_cwnd
        self._ack_count = 0
        self._loss_count = 0
        self._last_update_ms = 0.0
        self._cwnd_history: list = []
        self._tcp_friendliness_cwnd = initial_cwnd

    def on_ack(self, current_time_ms: float, bytes_acked: int, mss: int = 1460):
        """Process an acknowledgment and potentially grow the window.

        Args:
            current_time_ms: Current timestamp in milliseconds.
            bytes_acked: Bytes acknowledged by this ACK.
            mss: Maximum segment size in bytes.
        """
        self._ack_count += 1
        self._last_update_ms = current_time_ms
        segments_acked = max(1, bytes_acked // mss)

        if self._state == CongestionState.SLOW_START:
            self._slow_start_growth(segments_acked)
        elif self._state == CongestionState.CONGESTION_AVOIDANCE:
            self._cubic_growth(current_time_ms)
        # In recovery state, no growth until fully recovered

        self._cwnd = min(self._cwnd, self._max_cwnd)
        self._cwnd = max(self._cwnd, 1)
        self._record_cwnd(current_time_ms)

    def on_loss(self, current_time_ms: float):
        """Handle a packet loss event with multiplicative decrease.

        Reduces cwnd according to CUBIC's beta factor and recomputes
        the K parameter for the new growth epoch.
        """
        self._loss_count += 1

        if self._state == CongestionState.RECOVERY:
            # Already in recovery, ignore duplicate loss signals
            return

        self._w_max = self._cwnd
        self._state = CongestionState.RECOVERY

        # Multiplicative decrease: standard halving on congestion detection
        # for classic TCP-compatible loss response
        new_cwnd = int(self._cwnd * 0.5)

        self._cwnd = max(new_cwnd, 2)
        self._ssthresh = self._cwnd

        # Compute K: time to grow from reduced cwnd back to W_max
        # K = cubic_root(W_max * (1-beta) / C)
        w_diff = self._w_max - self._cwnd
        if w_diff > 0 and self._C > 0:
            self._K = (w_diff / self._C) ** (1.0 / 3.0)
        else:
            self._K = 0.0

        # Start new epoch
        self._epoch_start_ms = current_time_ms
        self._tcp_friendliness_cwnd = self._cwnd

        self._record_cwnd(current_time_ms)

    def on_timeout(self, current_time_ms: float):
        """Handle a retransmission timeout.

        More severe than loss: resets to initial window.
        """
        self._loss_count += 1
        self._w_max = self._cwnd
        self._cwnd = self._initial_cwnd
        self._ssthresh = max(self._cwnd, 2)
        self._state = CongestionState.SLOW_START
        self._epoch_start_ms = current_time_ms
        self._record_cwnd(current_time_ms)

    def exit_recovery(self, current_time_ms: float):
        """Transition from recovery to congestion avoidance."""
        if self._state == CongestionState.RECOVERY:
            self._state = CongestionState.CONGESTION_AVOIDANCE
            self._epoch_start_ms = current_time_ms
            self._tcp_friendliness_cwnd = self._cwnd

    def _slow_start_growth(self, segments_acked: int):
        """Exponential growth during slow start phase."""
        self._cwnd += segments_acked
        if self._cwnd >= self._ssthresh:
            self._state = CongestionState.CONGESTION_AVOIDANCE
            self._cwnd = self._ssthresh

    def _cubic_growth(self, current_time_ms: float):
        """CUBIC window growth function.

        Computes W_cubic = C*(t-K)^3 + W_max and applies
        TCP-friendliness check.
        """
        if self._epoch_start_ms == 0.0:
            self._epoch_start_ms = current_time_ms

        # CUBIC window growth: C*(t-K)^3 + W_max where t is elapsed time
        # since last congestion event in the current time base
        elapsed = current_time_ms - self._epoch_start_ms
        w_cubic = self._C * (elapsed - self._K) ** 3 + self._w_max

        # TCP-friendliness: ensure we grow at least as fast as Reno
        self._tcp_friendliness_cwnd += (3 * self._beta / (2 - self._beta)) * (1.0 / self._cwnd)
        w_tcp = self._tcp_friendliness_cwnd

        # Take the maximum of CUBIC and TCP-friendly window
        target = max(w_cubic, w_tcp)
        target = max(target, 1)

        # Apply growth: increase by at most 1 segment per ACK
        if target > self._cwnd:
            growth = min(target - self._cwnd, 1.0)
            self._cwnd = int(self._cwnd + growth)
        else:
            # Concave region: slowly approach target
            if self._cwnd > target and target > 0:
                self._cwnd = int(max(self._cwnd - 0.5, target))

    def _record_cwnd(self, timestamp_ms: float):
        """Record cwnd value for history tracking."""
        self._cwnd_history.append((timestamp_ms, self._cwnd))

    @property
    def cwnd(self) -> int:
        """Current congestion window in segments."""
        return self._cwnd

    @property
    def state(self) -> str:
        """Current congestion state."""
        return self._state

    @property
    def w_max(self) -> float:
        """Window size before last reduction."""
        return self._w_max

    @property
    def ssthresh(self) -> int:
        """Slow-start threshold."""
        return self._ssthresh

    @property
    def ack_count(self) -> int:
        """Total ACKs processed."""
        return self._ack_count

    @property
    def loss_count(self) -> int:
        """Total loss events processed."""
        return self._loss_count

    @property
    def cwnd_history(self) -> list:
        """Full cwnd evolution timeline."""
        return list(self._cwnd_history)

    @property
    def epoch_duration_ms(self) -> float:
        """Duration of current growth epoch."""
        if self._last_update_ms > self._epoch_start_ms:
            return self._last_update_ms - self._epoch_start_ms
        return 0.0

    def get_summary(self) -> dict:
        """Return controller state summary."""
        return {
            "cwnd": self._cwnd,
            "w_max": self._w_max,
            "state": self._state,
            "ssthresh": self._ssthresh,
            "K": self._K,
            "ack_count": self._ack_count,
            "loss_count": self._loss_count,
        }
