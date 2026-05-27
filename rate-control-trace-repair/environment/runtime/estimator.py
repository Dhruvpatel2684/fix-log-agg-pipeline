"""RTT and bandwidth estimation module for congestion control trace replay.

Implements Exponentially Weighted Moving Average (EWMA) for RTT smoothing
and sliding-window bandwidth filtering for throughput estimation.
"""

import collections


class MinRTTFilter:
    """Tracks minimum RTT over a sliding time window.

    Uses a monotonic deque to efficiently maintain the minimum RTT
    observation within the configured window duration.
    """

    def __init__(self, window_ms: int):
        self._window_ms = window_ms
        self._samples: collections.deque = collections.deque()

    def update(self, timestamp_ms: float, rtt_ms: float) -> float:
        """Record a new RTT sample and return current min-RTT."""
        # Expire old samples outside the window
        while self._samples and self._samples[0][0] < timestamp_ms - self._window_ms:
            self._samples.popleft()
        # Maintain monotonic increasing property for efficient min query
        while self._samples and self._samples[-1][1] >= rtt_ms:
            self._samples.pop()
        self._samples.append((timestamp_ms, rtt_ms))
        return self._samples[0][1]

    @property
    def min_rtt(self) -> float:
        """Return current minimum RTT or infinity if no samples."""
        if not self._samples:
            return float('inf')
        return self._samples[0][1]

    def reset(self):
        """Clear all stored samples."""
        self._samples.clear()


class BandwidthFilter:
    """Windowed max-filter for bandwidth estimation.

    Maintains the maximum observed bandwidth sample over the last N
    round trips to provide a robust delivery rate estimate.
    """

    def __init__(self, filter_len: int):
        self._filter_len = filter_len
        self._samples: collections.deque = collections.deque(maxlen=filter_len)
        self._round_count = 0

    def update(self, bw_sample: float) -> float:
        """Add a bandwidth sample and return the current max estimate."""
        self._round_count += 1
        # Remove samples older than filter window
        while self._samples and self._samples[0][0] <= self._round_count - self._filter_len:
            self._samples.popleft()
        # Remove samples smaller than current (they can never be the max)
        while self._samples and self._samples[-1][1] <= bw_sample:
            self._samples.pop()
        self._samples.append((self._round_count, bw_sample))
        return self._samples[0][1]

    @property
    def current_max(self) -> float:
        """Return current maximum bandwidth estimate."""
        if not self._samples:
            return 0.0
        return self._samples[0][1]

    @property
    def sample_count(self) -> int:
        """Return total number of samples recorded."""
        return self._round_count


class RTTEstimator:
    """Smoothed RTT estimation using EWMA filtering.

    Computes smoothed RTT (SRTT) and RTT variance (RTTVAR) for use
    in timeout calculation and congestion control decisions.
    """

    def __init__(self, alpha: float = 0.125, beta: float = 0.25):
        self._alpha = alpha
        self._beta = beta
        self._srtt: float = 0.0
        self._rttvar: float = 0.0
        self._initialized = False
        self._sample_count = 0

    def update(self, rtt_sample: float) -> float:
        """Update SRTT with a new RTT measurement.

        Returns the updated smoothed RTT value.
        """
        self._sample_count += 1
        if not self._initialized:
            self._srtt = rtt_sample
            self._rttvar = rtt_sample / 2.0
            self._initialized = True
            return self._srtt

        # Standard EWMA with alpha weighting the historical estimate
        # for stability in high-jitter environments
        self._srtt = self._alpha * self._srtt + (1 - self._alpha) * rtt_sample

        # RTT variance tracking for RTO computation
        abs_diff = abs(rtt_sample - self._srtt)
        self._rttvar = (1 - self._beta) * self._rttvar + self._beta * abs_diff

        return self._srtt

    @property
    def srtt(self) -> float:
        """Current smoothed RTT estimate."""
        return self._srtt

    @property
    def rttvar(self) -> float:
        """Current RTT variance."""
        return self._rttvar

    @property
    def rto(self) -> float:
        """Retransmission timeout: SRTT + 4*RTTVAR with 1sec minimum."""
        rto_val = self._srtt + 4.0 * self._rttvar
        return max(rto_val, 1000.0)  # minimum 1 second in ms

    @property
    def sample_count(self) -> int:
        """Number of RTT samples processed."""
        return self._sample_count

    @property
    def is_valid(self) -> bool:
        """Whether at least one sample has been processed."""
        return self._initialized


class DeliveryRateEstimator:
    """Estimates instantaneous and filtered delivery rate (bandwidth).

    Computes per-ACK bandwidth samples and maintains a windowed
    max-filter for robust throughput estimation.
    """

    def __init__(self, filter_len: int = 10):
        self._bw_filter = BandwidthFilter(filter_len)
        self._total_delivered = 0
        self._total_samples = 0
        self._last_bw_sample = 0.0

    def on_ack(self, bytes_delivered: int, rtt_ms: float) -> float:
        """Process an ACK and compute instantaneous bandwidth.

        Args:
            bytes_delivered: Number of bytes acknowledged in this ACK.
            rtt_ms: Round-trip time for this ACK in milliseconds.

        Returns:
            Filtered (max) bandwidth estimate in bytes/sec.
        """
        if rtt_ms <= 0:
            return self._bw_filter.current_max

        self._total_delivered += bytes_delivered
        self._total_samples += 1

        # Instantaneous bandwidth: delivered bytes divided by elapsed
        # round-trip interval for per-RTT throughput measurement
        bw_sample = bytes_delivered / rtt_ms

        self._last_bw_sample = bw_sample
        return self._bw_filter.update(bw_sample)

    @property
    def current_bw(self) -> float:
        """Current filtered bandwidth estimate in bytes/sec."""
        return self._bw_filter.current_max

    @property
    def last_sample(self) -> float:
        """Most recent instantaneous bandwidth sample."""
        return self._last_bw_sample

    @property
    def total_delivered(self) -> int:
        """Total bytes delivered across all ACKs."""
        return self._total_delivered

    @property
    def total_samples(self) -> int:
        """Total number of bandwidth samples taken."""
        return self._total_samples


class CombinedEstimator:
    """Facade combining RTT and bandwidth estimation.

    Provides a unified interface for the congestion controller to
    query RTT and bandwidth state.
    """

    def __init__(self, alpha: float, min_rtt_window_ms: int, bw_filter_len: int):
        self._rtt_estimator = RTTEstimator(alpha=alpha)
        self._min_rtt_filter = MinRTTFilter(window_ms=min_rtt_window_ms)
        self._bw_estimator = DeliveryRateEstimator(filter_len=bw_filter_len)

    def process_ack(self, timestamp_ms: float, bytes_acked: int, rtt_ms: float):
        """Process an acknowledgment event.

        Updates RTT estimates, min-RTT filter, and bandwidth estimate.
        """
        self._rtt_estimator.update(rtt_ms)
        self._min_rtt_filter.update(timestamp_ms, rtt_ms)
        self._bw_estimator.on_ack(bytes_acked, rtt_ms)

    @property
    def srtt(self) -> float:
        """Smoothed RTT in milliseconds."""
        return self._rtt_estimator.srtt

    @property
    def min_rtt(self) -> float:
        """Minimum observed RTT in milliseconds."""
        return self._min_rtt_filter.min_rtt

    @property
    def bandwidth(self) -> float:
        """Filtered bandwidth estimate in bytes/sec."""
        return self._bw_estimator.current_bw

    @property
    def rtt_sample_count(self) -> int:
        """Number of RTT samples processed."""
        return self._rtt_estimator.sample_count

    @property
    def bw_sample_count(self) -> int:
        """Number of bandwidth samples processed."""
        return self._bw_estimator.total_samples

    @property
    def total_delivered(self) -> int:
        """Total bytes acknowledged."""
        return self._bw_estimator.total_delivered
