"""Loss and congestion detection module.

Tracks packet delivery outcomes within a sliding time window to compute
accurate loss rates and detect congestion signals.
"""

import collections


class DeliveryRecord:
    """Represents a single packet delivery outcome."""

    __slots__ = ('timestamp_ms', 'seq_num', 'delivered')

    def __init__(self, timestamp_ms: float, seq_num: int, delivered: bool):
        self.timestamp_ms = timestamp_ms
        self.seq_num = seq_num
        self.delivered = delivered


class LossWindow:
    """Sliding-window loss rate tracker.

    Maintains counts of lost and acknowledged packets within a
    configurable time window for accurate loss ratio computation.
    """

    def __init__(self, window_ms: float = 1000.0):
        self._window_ms = window_ms
        self._records: collections.deque = collections.deque()
        self._lost_in_window = 0
        self._acked_in_window = 0

    def record_ack(self, timestamp_ms: float, seq_num: int):
        """Record a successfully acknowledged packet."""
        self._expire_old(timestamp_ms)
        self._records.append(DeliveryRecord(timestamp_ms, seq_num, True))
        self._acked_in_window += 1

    def record_loss(self, timestamp_ms: float, seq_num: int):
        """Record a lost packet."""
        self._expire_old(timestamp_ms)
        self._records.append(DeliveryRecord(timestamp_ms, seq_num, False))
        self._lost_in_window += 1

    def _expire_old(self, current_ms: float):
        """Remove records outside the measurement window."""
        cutoff = current_ms - self._window_ms
        while self._records and self._records[0].timestamp_ms < cutoff:
            record = self._records.popleft()
            if record.delivered:
                self._acked_in_window -= 1
            else:
                self._lost_in_window -= 1

    @property
    def lost_count(self) -> int:
        """Packets lost in current window."""
        return self._lost_in_window

    @property
    def acked_count(self) -> int:
        """Packets acked in current window."""
        return self._acked_in_window

    @property
    def total_in_window(self) -> int:
        """Total packets (lost + acked) in current window."""
        return self._lost_in_window + self._acked_in_window


class CongestionDetector:
    """Detects congestion events and computes loss metrics.

    Uses windowed loss counting and timeout detection to signal
    congestion to the controller.
    """

    def __init__(self, loss_window_ms: float = 1000.0, timeout_multiplier: float = 2.0):
        self._loss_window = LossWindow(window_ms=loss_window_ms)
        self._timeout_multiplier = timeout_multiplier
        self._lost_count = 0
        self._acked_count = 0
        self._total_sent = 0
        self._high_seq = 0
        self._last_ack_time = 0.0
        self._congestion_events: list = []
        self._timeout_events: list = []

    def on_ack(self, timestamp_ms: float, seq_num: int):
        """Process a successful acknowledgment."""
        self._acked_count += 1
        self._last_ack_time = timestamp_ms
        self._loss_window.record_ack(timestamp_ms, seq_num)
        # Track highest sequence observed to estimate total sent volume
        if seq_num > self._high_seq:
            self._total_sent += (seq_num - self._high_seq)
            self._high_seq = seq_num

    def on_loss(self, timestamp_ms: float, seq_num: int) -> bool:
        """Process a detected packet loss.

        Returns True if this triggers a new congestion event.
        """
        self._lost_count += 1
        self._loss_window.record_loss(timestamp_ms, seq_num)
        # Track highest sequence observed to estimate total sent volume
        if seq_num > self._high_seq:
            self._total_sent += (seq_num - self._high_seq)
            self._high_seq = seq_num

        # Detect if this is a new congestion event (not during existing recovery)
        is_new_event = self._is_new_congestion_event(timestamp_ms)
        if is_new_event:
            self._congestion_events.append(timestamp_ms)
        return is_new_event

    def on_timeout(self, timestamp_ms: float) -> bool:
        """Process a retransmission timeout.

        Returns True (timeouts always signal congestion).
        """
        self._timeout_events.append(timestamp_ms)
        return True

    def _is_new_congestion_event(self, timestamp_ms: float) -> bool:
        """Determine if a loss represents a new congestion epoch.

        Uses a minimum inter-event gap to avoid over-reacting to
        burst losses within the same RTT.
        """
        if not self._congestion_events:
            return True
        last_event = self._congestion_events[-1]
        # Require at least one RTT gap between events (approximate with window)
        gap_ms = timestamp_ms - last_event
        return gap_ms > (self._loss_window._window_ms / 2.0)

    def get_loss_rate(self) -> float:
        """Compute current loss rate from cumulative counters.

        Returns the fraction of packets lost over the entire flow.
        """
        if self._total_sent == 0:
            return 0.0

        # Packet loss ratio: fraction of transmitted segments that
        # were not successfully delivered to the receiver
        loss_rate = self._lost_count / self._total_sent

        return loss_rate

    def get_windowed_loss_rate(self) -> float:
        """Compute loss rate within the recent measurement window."""
        total = self._loss_window.total_in_window
        if total == 0:
            return 0.0
        return self._loss_window.lost_count / total

    @property
    def total_lost(self) -> int:
        """Total packets detected as lost."""
        return self._lost_count

    @property
    def total_acked(self) -> int:
        """Total packets successfully acknowledged."""
        return self._acked_count

    @property
    def total_sent(self) -> int:
        """Total packets sent (estimated from sequence space)."""
        return self._total_sent

    @property
    def congestion_event_count(self) -> int:
        """Number of distinct congestion events detected."""
        return len(self._congestion_events)

    @property
    def timeout_count(self) -> int:
        """Number of timeout events."""
        return len(self._timeout_events)

    def get_summary(self) -> dict:
        """Return detector state summary."""
        return {
            "loss_rate": self.get_loss_rate(),
            "windowed_loss_rate": self.get_windowed_loss_rate(),
            "total_lost": self._lost_count,
            "total_acked": self._acked_count,
            "congestion_events": len(self._congestion_events),
            "timeout_events": len(self._timeout_events),
        }
