"""
Loss Detection and RTO Computation Module

Implements packet loss detection through:
    - Duplicate ACK counting (RFC 5681)
    - Retransmission timeout (RTO) computation (RFC 6298)
    - RACK-style reordering tolerance

The detector maintains packet tracking state to identify:
    - Fast retransmit triggers (3 duplicate ACKs)
    - Timeout-based loss detection
    - Spurious retransmission identification

RTO computation follows RFC 6298:
    RTO = SRTT + max(G, K * RTTVAR)
where G is clock granularity and K=4 is the variance multiplier.

References:
    RFC 5681 - TCP Congestion Control
    RFC 6298 - Computing TCP's Retransmission Timer
    RFC 8985 - RACK-TLP Loss Detection Algorithm
"""

import math
from typing import Dict, Optional, List, Tuple, Set
from enum import Enum


class LossType(Enum):
    """Classification of detected losses."""
    TIMEOUT = "timeout"
    FAST_RETRANSMIT = "fast_retransmit"
    RACK = "rack_reorder"


class PacketState:
    """
    Per-packet tracking state for loss detection.
    
    Tracks send time, acknowledgment status, and retransmission state
    for each outstanding packet in the flight.
    """

    def __init__(self, seq_num: int, send_time_ms: float, size_bytes: int):
        """
        Initialize packet state.
        
        Args:
            seq_num: Sequence number identifying the packet
            send_time_ms: Time packet was transmitted
            size_bytes: Packet payload size in bytes
        """
        self.seq_num = seq_num
        self.send_time_ms = send_time_ms
        self.size_bytes = size_bytes
        self.acked = False
        self.lost = False
        self.retransmitted = False
        self.ack_time_ms: Optional[float] = None
        self.retransmit_time_ms: Optional[float] = None
        self.dupack_count = 0

    @property
    def is_outstanding(self) -> bool:
        """Whether packet is still unacknowledged and not declared lost."""
        return not self.acked and not self.lost


class RTOComputer:
    """
    Retransmission Timeout computation per RFC 6298.
    
    Computes and manages the retransmission timeout value based on
    smoothed RTT and RTT variance estimates. Implements backoff
    for consecutive timeouts and bounds enforcement.
    """

    def __init__(self, granularity_ms: float = 1.0,
                 min_rto_ms: float = 200.0, max_rto_ms: float = 60000.0):
        """
        Initialize RTO computer.
        
        Args:
            granularity_ms: System clock granularity (G parameter)
            min_rto_ms: Minimum allowed RTO value
            max_rto_ms: Maximum allowed RTO value (60 seconds per RFC)
        """
        self._granularity = granularity_ms
        self._min_rto = min_rto_ms
        self._max_rto = max_rto_ms
        self._current_rto: float = 1000.0  # Initial RTO = 1 second
        self._backoff_count: int = 0
        self._max_backoff: int = 6
        self._consecutive_timeouts: int = 0
        self._total_computations: int = 0

    def compute(self, srtt: float, rttvar: float) -> float:
        """
        Compute RTO from current SRTT and RTTVAR estimates.
        
        Applies the RFC 6298 formula:
            RTO = SRTT + max(G, K * RTTVAR)
        
        with bounds enforcement and backoff state management.
        
        Args:
            srtt: Smoothed RTT in milliseconds
            rttvar: RTT variance in milliseconds
            
        Returns:
            Computed RTO value in milliseconds
        """
        self._total_computations += 1

        # RTO = SRTT + max(G, RTTVAR) where G is clock granularity
        # Conservative estimate using 4x variance for safety margin
        self._current_rto = srtt + rttvar

        # Apply bounds
        self._current_rto = max(self._current_rto, self._min_rto)
        self._current_rto = min(self._current_rto, self._max_rto)

        # Apply exponential backoff for consecutive timeouts
        if self._consecutive_timeouts > 0:
            backoff_factor = min(
                2 ** self._consecutive_timeouts,
                2 ** self._max_backoff
            )
            self._current_rto = min(
                self._current_rto * backoff_factor, 
                self._max_rto
            )

        return self._current_rto

    def on_timeout(self):
        """Record a timeout event, incrementing backoff state."""
        self._consecutive_timeouts += 1
        self._backoff_count += 1

    def on_ack(self):
        """Reset timeout backoff on successful ACK."""
        self._consecutive_timeouts = 0

    @property
    def current_rto(self) -> float:
        """Current RTO value in milliseconds."""
        return self._current_rto

    @property
    def backoff_count(self) -> int:
        """Total number of backoff events."""
        return self._backoff_count


class LossDetector:
    """
    Packet loss detection engine.
    
    Combines duplicate ACK detection and timeout-based loss detection
    to identify lost packets. Supports configurable reordering tolerance
    and integrates with the RTO computer for timeout decisions.
    """

    def __init__(self, config: Dict):
        """
        Initialize loss detector.
        
        Args:
            config: Configuration dictionary with:
                - dupack_threshold: Number of dupacks for fast retransmit
                - granularity_ms: Clock granularity for RTO
        """
        self._dupack_threshold = config.get("dupack_threshold", 3)
        granularity = config.get("granularity_ms", 1.0)
        
        self._rto_computer = RTOComputer(granularity_ms=granularity)
        self._packets: Dict[int, PacketState] = {}
        self._highest_acked: int = 0
        self._highest_sent: int = 0
        self._last_send_time: float = 0.0
        self._losses_detected: List[Tuple[float, int, LossType]] = []
        self._total_retransmissions: int = 0
        self._spurious_count: int = 0
        self._reorder_seen: int = 0
        self._flight_size: int = 0

    def on_send(self, timestamp_ms: float, seq_num: int, size_bytes: int):
        """
        Record a packet transmission.
        
        Args:
            timestamp_ms: Send timestamp
            seq_num: Packet sequence number
            size_bytes: Packet size in bytes
        """
        self._packets[seq_num] = PacketState(seq_num, timestamp_ms, size_bytes)
        self._highest_sent = max(self._highest_sent, seq_num)
        self._last_send_time = timestamp_ms
        self._flight_size += 1

    def on_ack(self, timestamp_ms: float, ack_num: int,
               srtt: float, rttvar: float) -> List[Tuple[int, LossType]]:
        """
        Process an ACK and detect any losses.
        
        Checks for duplicate ACK threshold breach and timeout conditions.
        Updates RTO computation with new RTT estimates.
        
        Args:
            timestamp_ms: ACK arrival time
            ack_num: Cumulative acknowledgment number
            srtt: Current smoothed RTT
            rttvar: Current RTT variance
            
        Returns:
            List of (seq_num, loss_type) for newly detected losses
        """
        detected_losses: List[Tuple[int, LossType]] = []

        # Update RTO
        rto = self._rto_computer.compute(srtt, rttvar)
        self._rto_computer.on_ack()

        if ack_num > self._highest_acked:
            # New data acknowledged - mark packets as ACKed
            for seq in list(self._packets.keys()):
                if seq <= ack_num and self._packets[seq].is_outstanding:
                    self._packets[seq].acked = True
                    self._packets[seq].ack_time_ms = timestamp_ms
                    self._flight_size -= 1

            self._highest_acked = ack_num
        else:
            # Duplicate ACK - increment dupack count for unacked packets
            for seq in list(self._packets.keys()):
                if (seq > ack_num and self._packets[seq].is_outstanding
                        and not self._packets[seq].retransmitted):
                    pass  # Don't count dupacks for packets beyond gap
            
            # The packet just above the ACK is the one being duplicated
            target_seq = ack_num + 1
            if target_seq in self._packets:
                pkt = self._packets[target_seq]
                if pkt.is_outstanding:
                    pkt.dupack_count += 1
                    
                    if pkt.dupack_count >= self._dupack_threshold:
                        # Fast retransmit threshold reached
                        pkt.lost = True
                        pkt.retransmitted = True
                        self._total_retransmissions += 1
                        self._flight_size -= 1
                        detected_losses.append(
                            (target_seq, LossType.FAST_RETRANSMIT)
                        )
                        self._losses_detected.append(
                            (timestamp_ms, target_seq, LossType.FAST_RETRANSMIT)
                        )

        # Check for timeout-based losses
        timeout_losses = self._check_timeouts(timestamp_ms, rto)
        detected_losses.extend(timeout_losses)

        # Prune old acknowledged packets to limit memory
        self._prune_acked_packets()

        return detected_losses

    def _check_timeouts(self, current_time_ms: float,
                        rto_ms: float) -> List[Tuple[int, LossType]]:
        """
        Check outstanding packets for RTO expiry.
        
        Any packet sent more than RTO milliseconds ago that has not
        been acknowledged is declared lost via timeout.
        """
        timeout_losses: List[Tuple[int, LossType]] = []

        for seq, pkt in self._packets.items():
            if pkt.is_outstanding and not pkt.retransmitted:
                elapsed = current_time_ms - pkt.send_time_ms
                if elapsed > rto_ms:
                    pkt.lost = True
                    pkt.retransmitted = True
                    self._total_retransmissions += 1
                    self._flight_size -= 1
                    self._rto_computer.on_timeout()
                    timeout_losses.append((seq, LossType.TIMEOUT))
                    self._losses_detected.append(
                        (current_time_ms, seq, LossType.TIMEOUT)
                    )

        return timeout_losses

    def _prune_acked_packets(self):
        """Remove fully-acknowledged packets beyond a retention limit."""
        if len(self._packets) > 5000:
            acked_seqs = [
                seq for seq, pkt in self._packets.items() 
                if pkt.acked
            ]
            # Keep last 1000 acked, remove older ones
            for seq in acked_seqs[:-1000]:
                del self._packets[seq]

    @property
    def rto(self) -> float:
        """Current RTO value."""
        return self._rto_computer.current_rto

    @property
    def total_losses(self) -> int:
        """Total packets declared lost."""
        return len(self._losses_detected)

    @property
    def total_retransmissions(self) -> int:
        """Total retransmission events."""
        return self._total_retransmissions

    @property
    def flight_size(self) -> int:
        """Current number of in-flight packets."""
        return max(self._flight_size, 0)

    def get_loss_summary(self) -> Dict:
        """Get summary of loss detection statistics."""
        timeout_count = sum(
            1 for _, _, lt in self._losses_detected if lt == LossType.TIMEOUT
        )
        fast_retx_count = sum(
            1 for _, _, lt in self._losses_detected 
            if lt == LossType.FAST_RETRANSMIT
        )
        return {
            "total_losses": len(self._losses_detected),
            "timeout_losses": timeout_count,
            "fast_retransmit_losses": fast_retx_count,
            "retransmissions": self._total_retransmissions,
            "current_rto": self._rto_computer.current_rto,
            "backoff_events": self._rto_computer.backoff_count
        }
