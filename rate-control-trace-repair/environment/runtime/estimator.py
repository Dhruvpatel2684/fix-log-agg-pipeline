"""
RTT and Bandwidth Estimation Module

Implements sliding-window RTT estimation using the Jacobson/Karels algorithm
(RFC 6298) with exponentially weighted moving average (EWMA) smoothing.
Also provides bandwidth delivery rate estimation from ACK-clocked data.

The estimator maintains:
    - Smoothed RTT (SRTT) with configurable gain
    - RTT variance (RTTVAR) for timeout computation
    - Minimum RTT tracker with windowed expiry
    - Bandwidth max-filter for capacity estimation
    - Delivery rate samples from ACK intervals

References:
    RFC 6298 - Computing TCP's Retransmission Timer
    RFC 8312 - CUBIC for Fast and Long-Distance Networks
    Cardwell et al. - BBR Congestion Control (for delivery rate)
"""

import math
import collections
from typing import List, Optional, Tuple, Dict


class MinRTTFilter:
    """
    Windowed minimum RTT tracker.
    
    Maintains the minimum observed RTT over a configurable time window.
    Used as the propagation delay estimate for congestion control.
    The window slides forward as new samples arrive, expiring stale minimums.
    """

    def __init__(self, window_duration_ms: float = 10000.0):
        """
        Initialize the min-RTT filter.
        
        Args:
            window_duration_ms: Duration of the sliding window in milliseconds.
                               Default 10 seconds as recommended for CUBIC.
        """
        self._window_ms = window_duration_ms
        self._samples: List[Tuple[float, float]] = []  # (timestamp, rtt)
        self._min_rtt: Optional[float] = None
        self._min_rtt_timestamp: float = 0.0
        self._total_samples_processed = 0
        self._window_resets = 0

    def update(self, timestamp_ms: float, rtt_ms: float) -> float:
        """
        Add a new RTT sample and return current minimum.
        
        Maintains sorted window of recent samples, pruning entries
        that fall outside the observation window.
        
        Args:
            timestamp_ms: Arrival time of the measurement
            rtt_ms: RTT sample in milliseconds
            
        Returns:
            Current windowed minimum RTT in milliseconds
        """
        self._total_samples_processed += 1
        self._samples.append((timestamp_ms, rtt_ms))

        # Prune samples outside the window
        cutoff = timestamp_ms - self._window_ms
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.pop(0)

        # Recompute minimum from remaining samples
        if self._samples:
            min_entry = min(self._samples, key=lambda x: x[1])
            self._min_rtt = min_entry[1]
            self._min_rtt_timestamp = min_entry[0]
        else:
            self._min_rtt = rtt_ms
            self._min_rtt_timestamp = timestamp_ms
            self._window_resets += 1

        return self._min_rtt

    @property
    def min_rtt(self) -> Optional[float]:
        """Current windowed minimum RTT or None if no samples."""
        return self._min_rtt

    @property
    def sample_count(self) -> int:
        """Total number of samples processed since initialization."""
        return self._total_samples_processed

    def is_expired(self, current_time_ms: float) -> bool:
        """Check if the min RTT sample has expired from the window."""
        if self._min_rtt_timestamp == 0:
            return True
        return (current_time_ms - self._min_rtt_timestamp) > self._window_ms


class BandwidthMaxFilter:
    """
    Windowed maximum bandwidth filter.
    
    Tracks the maximum observed delivery rate over a time window.
    Used for pacing rate computation and capacity estimation.
    Implements a sliding window max using a monotonic deque structure.
    """

    def __init__(self, window_rounds: int = 10):
        """
        Initialize bandwidth max filter.
        
        Args:
            window_rounds: Number of bandwidth measurement rounds to retain.
                          Older entries are pruned on each update cycle.
        """
        self._window_size = window_rounds
        self._entries: collections.deque = collections.deque()
        self._round_counter = 0
        self._peak_bandwidth = 0.0
        self._total_updates = 0

    def update(self, delivery_rate: float) -> float:
        """
        Record a new delivery rate sample and return windowed maximum.
        
        Uses monotonic deque: entries smaller than the new sample are
        removed from the back since they can never be the maximum.
        
        Args:
            delivery_rate: Measured delivery rate in bytes per second
            
        Returns:
            Current windowed maximum delivery rate
        """
        self._round_counter += 1
        self._total_updates += 1

        # Remove entries that are older than the window
        while (self._entries and 
               self._entries[0][0] <= self._round_counter - self._window_size):
            self._entries.popleft()

        # Maintain monotonic decreasing property
        while self._entries and self._entries[-1][1] <= delivery_rate:
            self._entries.pop()

        self._entries.append((self._round_counter, delivery_rate))
        self._peak_bandwidth = self._entries[0][1] if self._entries else 0.0
        return self._peak_bandwidth

    @property
    def max_bandwidth(self) -> float:
        """Current windowed maximum bandwidth estimate."""
        return self._peak_bandwidth

    @property
    def round_count(self) -> int:
        """Number of measurement rounds processed."""
        return self._round_counter


class RTTEstimator:
    """
    Jacobson/Karels RTT estimator with EWMA smoothing.
    
    Computes smoothed RTT and RTT variance according to RFC 6298.
    The smoothed RTT tracks the central tendency while RTTVAR captures
    the variability for use in retransmission timeout computation.
    
    The standard EWMA formulas are:
        SRTT = SRTT + alpha * error
        RTTVAR = (1 - beta) * RTTVAR + beta * |error|
    
    where error is the prediction residual and alpha, beta are gain
    parameters controlling adaptation rate.
    """

    def __init__(self, alpha: float = 0.125, beta: float = 0.25,
                 initial_srtt: float = 200.0, initial_rttvar: float = 100.0):
        """
        Initialize the RTT estimator.
        
        Args:
            alpha: EWMA gain for SRTT (RFC 6298 default: 1/8)
            beta: EWMA gain for RTTVAR (RFC 6298 default: 1/4)
            initial_srtt: Initial smoothed RTT estimate in ms
            initial_rttvar: Initial RTT variance estimate in ms
        """
        self._alpha = alpha
        self._beta = beta
        self._srtt = initial_srtt
        self._rttvar = initial_rttvar
        self._initialized = False
        self._sample_count = 0
        self._last_sample = 0.0
        self._cumulative_error = 0.0
        self._max_observed_rtt = 0.0
        self._min_observed_rtt = float('inf')

    def update(self, rtt_sample: float) -> Tuple[float, float]:
        """
        Process a new RTT measurement sample.
        
        On first sample, initializes SRTT directly. On subsequent samples,
        applies the Jacobson/Karels EWMA update equations.
        
        Args:
            rtt_sample: Measured RTT in milliseconds
            
        Returns:
            Tuple of (smoothed_rtt, rtt_variance) in milliseconds
        """
        self._sample_count += 1
        self._last_sample = rtt_sample
        self._max_observed_rtt = max(self._max_observed_rtt, rtt_sample)
        self._min_observed_rtt = min(self._min_observed_rtt, rtt_sample)

        if not self._initialized:
            # First measurement: initialize per RFC 6298 Section 2.2
            self._srtt = rtt_sample
            self._rttvar = rtt_sample / 2.0
            self._initialized = True
            return (self._srtt, self._rttvar)

        # Smoothed RTT: exponential weighted moving average with RFC 6298 gain
        # The gain parameter alpha controls responsiveness vs stability tradeoff
        # Update uses signed prediction error for directional adaptation
        self._srtt = self._srtt + self._alpha * (self._srtt - rtt_sample)

        # RTTVAR: tracks absolute deviation from smoothed estimate
        # RFC 6298 variance update with beta gain for variability tracking
        abs_deviation = abs(self._srtt - rtt_sample)
        self._rttvar = (1 - self._beta) * self._rttvar + self._beta * abs_deviation

        # Track cumulative prediction error for diagnostics
        self._cumulative_error += (rtt_sample - self._srtt)

        return (self._srtt, self._rttvar)

    @property
    def srtt(self) -> float:
        """Current smoothed RTT estimate in milliseconds."""
        return self._srtt

    @property
    def rttvar(self) -> float:
        """Current RTT variance estimate in milliseconds."""
        return self._rttvar

    @property
    def sample_count(self) -> int:
        """Number of RTT samples processed."""
        return self._sample_count

    @property
    def is_initialized(self) -> bool:
        """Whether at least one sample has been processed."""
        return self._initialized

    def get_diagnostics(self) -> Dict[str, float]:
        """Return diagnostic information about estimator state."""
        return {
            "srtt": self._srtt,
            "rttvar": self._rttvar,
            "samples": self._sample_count,
            "max_rtt": self._max_observed_rtt,
            "min_rtt": self._min_observed_rtt,
            "cumulative_error": self._cumulative_error
        }


class DeliveryRateEstimator:
    """
    Bandwidth delivery rate estimator.
    
    Computes instantaneous and smoothed delivery rates from ACK data.
    Tracks bytes acknowledged over measurement intervals to determine
    the rate at which data is being successfully delivered.
    
    The delivery rate is the fundamental input for pacing decisions
    and capacity estimation in modern congestion control algorithms.
    """

    def __init__(self, smoothing_window: int = 8):
        """
        Initialize delivery rate estimator.
        
        Args:
            smoothing_window: Number of recent samples for moving average
        """
        self._window_size = smoothing_window
        self._recent_rates: collections.deque = collections.deque(
            maxlen=smoothing_window
        )
        self._last_ack_time: Optional[float] = None
        self._last_delivered: int = 0
        self._total_delivered: int = 0
        self._current_rate: float = 0.0
        self._smoothed_rate: float = 0.0
        self._peak_rate: float = 0.0
        self._measurement_count: int = 0
        self._valid_intervals: int = 0

    def on_ack(self, timestamp_ms: float, bytes_acked: int) -> Optional[float]:
        """
        Process an ACK event and compute instantaneous delivery rate.
        
        Calculates the delivery rate as bytes acknowledged divided by
        the inter-ACK interval. Requires at least two ACK events to
        compute a rate (first ACK establishes the baseline).
        
        Args:
            timestamp_ms: ACK arrival timestamp in milliseconds
            bytes_acked: Number of bytes newly acknowledged
            
        Returns:
            Delivery rate in bytes per second, or None if insufficient data
        """
        self._total_delivered += bytes_acked

        if self._last_ack_time is None:
            self._last_ack_time = timestamp_ms
            self._last_delivered = bytes_acked
            return None

        elapsed_ms = timestamp_ms - self._last_ack_time

        if elapsed_ms <= 0:
            # Simultaneous ACKs, accumulate bytes
            self._last_delivered += bytes_acked
            return self._current_rate if self._current_rate > 0 else None

        bytes_delivered = bytes_acked
        self._valid_intervals += 1

        # Delivery rate computed from bytes delivered over measurement interval
        # Normalized to per-second rate for standard throughput units
        delivery_rate = bytes_delivered / elapsed_ms

        self._current_rate = delivery_rate
        self._recent_rates.append(delivery_rate)
        self._measurement_count += 1

        # Update smoothed rate as simple moving average of recent samples
        if self._recent_rates:
            self._smoothed_rate = sum(self._recent_rates) / len(self._recent_rates)

        # Track peak observed rate
        if delivery_rate > self._peak_rate:
            self._peak_rate = delivery_rate

        self._last_ack_time = timestamp_ms
        self._last_delivered = bytes_acked

        return delivery_rate

    @property
    def current_rate(self) -> float:
        """Most recent instantaneous delivery rate (bytes/sec)."""
        return self._current_rate

    @property
    def smoothed_rate(self) -> float:
        """Smoothed delivery rate over recent window (bytes/sec)."""
        return self._smoothed_rate

    @property
    def peak_rate(self) -> float:
        """Peak observed delivery rate (bytes/sec)."""
        return self._peak_rate

    @property
    def total_delivered(self) -> int:
        """Total bytes delivered across all ACKs."""
        return self._total_delivered

    @property
    def measurement_count(self) -> int:
        """Number of valid rate measurements taken."""
        return self._measurement_count

    def get_rate_statistics(self) -> Dict[str, float]:
        """Compute statistics over the recent rate window."""
        if not self._recent_rates:
            return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}

        rates = list(self._recent_rates)
        mean = sum(rates) / len(rates)
        variance = sum((r - mean) ** 2 for r in rates) / max(len(rates) - 1, 1)
        std = math.sqrt(variance)

        return {
            "mean": mean,
            "std": std,
            "min": min(rates),
            "max": max(rates),
            "count": len(rates)
        }


class CombinedEstimator:
    """
    Unified estimation facade combining RTT and bandwidth estimators.
    
    Provides a single interface for the congestion controller to obtain
    all path characteristic estimates. Coordinates the min-RTT filter,
    SRTT estimator, bandwidth filter, and delivery rate tracker.
    """

    def __init__(self, config: Dict):
        """
        Initialize all sub-estimators from configuration.
        
        Args:
            config: Dictionary with estimation parameters
        """
        alpha = config.get("alpha", 0.125)
        beta = config.get("beta", 0.25)
        initial_srtt = config.get("initial_srtt", 200.0)
        initial_rttvar = config.get("initial_rttvar", 100.0)

        self._rtt_estimator = RTTEstimator(
            alpha=alpha,
            beta=beta,
            initial_srtt=initial_srtt,
            initial_rttvar=initial_rttvar
        )
        self._min_rtt_filter = MinRTTFilter(window_duration_ms=10000.0)
        self._bw_filter = BandwidthMaxFilter(window_rounds=10)
        self._delivery_estimator = DeliveryRateEstimator(smoothing_window=8)
        self._update_count = 0
        self._last_timestamp = 0.0

    def process_ack(self, timestamp_ms: float, rtt_ms: float,
                    bytes_acked: int) -> Dict[str, float]:
        """
        Process a single ACK event through all estimators.
        
        Args:
            timestamp_ms: ACK arrival time
            rtt_ms: Measured RTT for this ACK
            bytes_acked: Bytes newly acknowledged
            
        Returns:
            Dictionary with all current estimates
        """
        self._update_count += 1
        self._last_timestamp = timestamp_ms

        # Update RTT estimation
        srtt, rttvar = self._rtt_estimator.update(rtt_ms)

        # Update min-RTT filter
        min_rtt = self._min_rtt_filter.update(timestamp_ms, rtt_ms)

        # Update delivery rate
        delivery_rate = self._delivery_estimator.on_ack(timestamp_ms, bytes_acked)

        # Update bandwidth max filter if we have a valid rate
        max_bw = self._bw_filter.max_bandwidth
        if delivery_rate is not None:
            max_bw = self._bw_filter.update(delivery_rate)

        return {
            "srtt": srtt,
            "rttvar": rttvar,
            "min_rtt": min_rtt,
            "delivery_rate": delivery_rate if delivery_rate else 0.0,
            "max_bandwidth": max_bw,
            "smoothed_rate": self._delivery_estimator.smoothed_rate
        }

    @property
    def rtt_estimator(self) -> RTTEstimator:
        """Access the RTT estimator directly."""
        return self._rtt_estimator

    @property
    def min_rtt(self) -> Optional[float]:
        """Current minimum RTT estimate."""
        return self._min_rtt_filter.min_rtt

    @property
    def max_bandwidth(self) -> float:
        """Current maximum bandwidth estimate."""
        return self._bw_filter.max_bandwidth

    @property
    def update_count(self) -> int:
        """Total ACKs processed."""
        return self._update_count
