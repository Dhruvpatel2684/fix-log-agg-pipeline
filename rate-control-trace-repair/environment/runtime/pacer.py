"""
Token Bucket Pacing Engine

Implements packet pacing using a token bucket model to smooth burst
transmissions and achieve more uniform packet spacing. Pacing helps
reduce network queue oscillation and improves throughput stability.

The pacer operates by:
    1. Computing a target pacing rate from cwnd and RTT
    2. Replenishing tokens at the pacing rate
    3. Allowing sends only when sufficient tokens are available
    4. Supporting burst allowance for initial ramp-up

Token bucket parameters:
    - Capacity: Maximum burst size (tokens)
    - Rate: Token replenishment rate (segments/second)
    - Deficit: Accumulated send debt when rate-limited

References:
    BBR Congestion Control - Pacing implementation
    RFC 3448 - TCP Friendly Rate Control
    Linux kernel pacing implementation (net/ipv4/tcp_output.c)
"""

import math
from typing import Dict, Optional, List, Tuple


class TokenBucket:
    """
    Standard token bucket rate limiter.
    
    Accumulates tokens at a configured rate up to a maximum capacity.
    Each send attempt consumes tokens; sends are denied when the bucket
    is empty until sufficient tokens accumulate.
    """

    def __init__(self, capacity: float = 10.0, initial_tokens: float = 10.0):
        """
        Initialize token bucket.
        
        Args:
            capacity: Maximum number of tokens (burst limit)
            initial_tokens: Starting token count
        """
        self._capacity = capacity
        self._tokens = min(initial_tokens, capacity)
        self._last_refill_time: float = 0.0
        self._total_consumed: float = 0.0
        self._total_refilled: float = 0.0
        self._denials: int = 0
        self._grants: int = 0

    def refill(self, elapsed_ms: float, rate: float) -> float:
        """
        Add tokens based on elapsed time and current rate.
        
        Tokens are accumulated proportional to elapsed time at the
        configured pacing rate. The bucket cannot exceed capacity.
        
        Args:
            elapsed_ms: Time since last refill in milliseconds
            rate: Current pacing rate in segments per second
            
        Returns:
            Number of tokens added
        """
        if elapsed_ms <= 0 or rate <= 0:
            return 0.0

        # Tokens replenished based on elapsed time and target rate
        # Rate is segments per millisecond for fine-grained pacing
        tokens_added = elapsed_ms * rate

        old_tokens = self._tokens
        self._tokens = min(self._tokens + tokens_added, self._capacity)
        actual_added = self._tokens - old_tokens
        self._total_refilled += actual_added

        return actual_added

    def consume(self, count: float = 1.0) -> bool:
        """
        Attempt to consume tokens for a send event.
        
        Args:
            count: Number of tokens to consume (usually 1 per segment)
            
        Returns:
            True if tokens were available and consumed, False if denied
        """
        if self._tokens >= count:
            self._tokens -= count
            self._total_consumed += count
            self._grants += 1
            return True
        else:
            self._denials += 1
            return False

    @property
    def available(self) -> float:
        """Current token count."""
        return self._tokens

    @property
    def capacity(self) -> float:
        """Maximum token capacity."""
        return self._capacity

    @property
    def utilization(self) -> float:
        """Fraction of tokens currently available."""
        return self._tokens / self._capacity if self._capacity > 0 else 0.0

    @property
    def grant_rate(self) -> float:
        """Fraction of requests that were granted."""
        total = self._grants + self._denials
        return self._grants / total if total > 0 else 1.0

    def get_stats(self) -> Dict[str, float]:
        """Get token bucket statistics."""
        return {
            "tokens": self._tokens,
            "capacity": self._capacity,
            "total_consumed": self._total_consumed,
            "total_refilled": self._total_refilled,
            "grants": self._grants,
            "denials": self._denials
        }


class PacingEngine:
    """
    Congestion-control-aware pacing engine.
    
    Computes pacing rate from congestion window and RTT estimates,
    then uses a token bucket to enforce smooth packet transmission.
    Supports configurable gain factors for probing and draining phases.
    
    The pacing rate is derived as:
        rate = cwnd / RTT * gain
    
    This ensures packets are spread evenly across each RTT rather
    than being sent in bursts that overwhelm intermediate queues.
    """

    def __init__(self, config: Dict):
        """
        Initialize pacing engine.
        
        Args:
            config: Configuration dictionary with:
                - default_gain: Normal pacing gain (typically 1.0)
                - probe_gain: Gain during bandwidth probing (>1.0)
        """
        self._default_gain = config.get("default_gain", 1.0)
        self._probe_gain = config.get("probe_gain", 1.25)
        self._current_gain = self._default_gain
        
        # Token bucket with capacity for initial burst
        self._bucket = TokenBucket(capacity=10.0, initial_tokens=10.0)
        
        # Pacing rate state
        self._pacing_rate: float = 0.0  # segments per second
        self._last_update_time: float = 0.0
        self._cwnd_estimate: float = 10.0
        self._rtt_estimate_ms: float = 100.0
        
        # Scheduling state
        self._next_send_time: float = 0.0
        self._inter_packet_interval: float = 0.0
        self._scheduled_sends: int = 0
        self._actual_sends: int = 0
        self._paced_delays: List[float] = []
        
        # Burst tracking
        self._burst_count: int = 0
        self._max_burst_size: int = 0
        self._current_burst: int = 0
        self._burst_start_time: float = 0.0

    def update_rate(self, cwnd: float, rtt_ms: float, 
                    timestamp_ms: float) -> float:
        """
        Recompute pacing rate from current cwnd and RTT.
        
        The pacing rate determines how quickly the token bucket
        refills, controlling the inter-packet spacing.
        
        Args:
            cwnd: Current congestion window in segments
            rtt_ms: Current RTT estimate in milliseconds
            timestamp_ms: Current time for rate computation
            
        Returns:
            New pacing rate in segments per second
        """
        self._cwnd_estimate = cwnd
        self._rtt_estimate_ms = max(rtt_ms, 1.0)  # Avoid division by zero

        # Base pacing rate: spread cwnd evenly over one RTT
        # Convert to segments per second for standard rate units
        rtt_sec = self._rtt_estimate_ms / 1000.0
        self._pacing_rate = (cwnd / rtt_sec) * self._current_gain

        # Compute inter-packet interval for scheduling
        if self._pacing_rate > 0:
            self._inter_packet_interval = 1000.0 / self._pacing_rate  # ms
        else:
            self._inter_packet_interval = float('inf')

        # Refill tokens based on elapsed time since last update
        if self._last_update_time > 0:
            elapsed = timestamp_ms - self._last_update_time
            self._bucket.refill(elapsed, self._pacing_rate)

        self._last_update_time = timestamp_ms

        return self._pacing_rate

    def should_send(self, timestamp_ms: float) -> bool:
        """
        Determine if a packet should be sent at this time.
        
        Checks token availability and timing constraints to decide
        whether sending is permitted under current pacing.
        
        Args:
            timestamp_ms: Current timestamp
            
        Returns:
            True if sending is allowed, False if pacing requires waiting
        """
        self._scheduled_sends += 1

        # Refill tokens if time has elapsed
        if self._last_update_time > 0:
            elapsed = timestamp_ms - self._last_update_time
            if elapsed > 0:
                self._bucket.refill(elapsed, self._pacing_rate)
                self._last_update_time = timestamp_ms

        # Check if we have tokens
        if self._bucket.consume(1.0):
            self._actual_sends += 1
            self._current_burst += 1
            
            # Track burst statistics
            if self._current_burst > self._max_burst_size:
                self._max_burst_size = self._current_burst
                
            return True
        else:
            # Rate limited - record delay
            if self._pacing_rate > 0:
                wait_time = 1000.0 / self._pacing_rate
                self._paced_delays.append(wait_time)
            
            # Reset burst counter on pacing pause
            if self._current_burst > 0:
                self._burst_count += 1
            self._current_burst = 0
            
            return False

    def set_probe_mode(self, probing: bool):
        """
        Enable or disable probe gain for bandwidth discovery.
        
        Args:
            probing: True to use probe gain, False for default gain
        """
        self._current_gain = self._probe_gain if probing else self._default_gain

    @property
    def pacing_rate(self) -> float:
        """Current pacing rate in segments per second."""
        return self._pacing_rate

    @property
    def inter_packet_interval(self) -> float:
        """Current inter-packet interval in milliseconds."""
        return self._inter_packet_interval

    @property
    def token_bucket(self) -> TokenBucket:
        """Access the underlying token bucket."""
        return self._bucket

    def get_pacing_stats(self) -> Dict:
        """Get comprehensive pacing statistics."""
        avg_delay = (sum(self._paced_delays) / len(self._paced_delays)
                     if self._paced_delays else 0.0)
        return {
            "pacing_rate": self._pacing_rate,
            "gain": self._current_gain,
            "cwnd": self._cwnd_estimate,
            "rtt_ms": self._rtt_estimate_ms,
            "inter_packet_ms": self._inter_packet_interval,
            "scheduled": self._scheduled_sends,
            "actual": self._actual_sends,
            "paced_fraction": 1.0 - (self._actual_sends / max(self._scheduled_sends, 1)),
            "avg_paced_delay_ms": avg_delay,
            "max_burst": self._max_burst_size,
            "burst_count": self._burst_count,
            "bucket_tokens": self._bucket.available,
            "bucket_grant_rate": self._bucket.grant_rate
        }
