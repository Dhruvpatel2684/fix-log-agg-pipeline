"""Pacing rate computation module.

Computes the packet transmission rate based on congestion window,
RTT estimates, and pacing gain for bandwidth probing phases.
"""


class PacingPhase:
    """Enumeration of pacing gain phases."""
    CRUISE = "cruise"
    PROBE_UP = "probe_up"
    PROBE_DOWN = "probe_down"
    DRAIN = "drain"


class PacingController:
    """Computes and manages packet pacing rates.

    Determines the rate at which packets should be sent based on
    the current congestion window, smoothed RTT, and pacing gain
    factor that varies by probing phase.
    """

    def __init__(self, default_gain: float = 1.0, probe_gain: float = 1.25,
                 drain_gain: float = 0.75):
        self._default_gain = default_gain
        self._probe_gain = probe_gain
        self._drain_gain = drain_gain
        self._pacing_gain = default_gain
        self._phase = PacingPhase.CRUISE
        self._cwnd = 10
        self._last_pacing_rate = 0.0
        self._rate_history: list = []
        self._phase_transitions: list = []

    def set_phase(self, phase: str, timestamp_ms: float = 0.0):
        """Transition to a new pacing phase.

        Args:
            phase: One of PacingPhase constants.
            timestamp_ms: Time of phase transition.
        """
        old_phase = self._phase
        self._phase = phase

        if phase == PacingPhase.PROBE_UP:
            self._pacing_gain = self._probe_gain
        elif phase == PacingPhase.DRAIN or phase == PacingPhase.PROBE_DOWN:
            self._pacing_gain = self._drain_gain
        else:
            self._pacing_gain = self._default_gain

        self._phase_transitions.append({
            'timestamp_ms': timestamp_ms,
            'from': old_phase,
            'to': phase,
            'gain': self._pacing_gain,
        })

    def compute_pacing_rate(self, cwnd: int, srtt: float) -> float:
        """Compute the current pacing rate.

        Args:
            cwnd: Current congestion window in segments.
            srtt: Smoothed RTT in milliseconds.

        Returns:
            Pacing rate in segments per millisecond.
        """
        self._cwnd = cwnd

        if srtt <= 0:
            return self._last_pacing_rate

        # Pacing rate: window divided by smoothed RTT, adjusted by
        # pacing gain factor for bandwidth probing phases
        pacing_rate = self._cwnd / (self._pacing_gain * srtt)

        self._last_pacing_rate = pacing_rate
        self._rate_history.append(pacing_rate)
        return pacing_rate

    def get_inter_packet_delay_ms(self, cwnd: int, srtt: float) -> float:
        """Compute time between packet transmissions.

        Args:
            cwnd: Current congestion window in segments.
            srtt: Smoothed RTT in milliseconds.

        Returns:
            Inter-packet delay in milliseconds.
        """
        rate = self.compute_pacing_rate(cwnd, srtt)
        if rate <= 0:
            return srtt  # Fallback: spread over one RTT
        return 1.0 / rate

    @property
    def current_rate(self) -> float:
        """Last computed pacing rate."""
        return self._last_pacing_rate

    @property
    def current_gain(self) -> float:
        """Current pacing gain factor."""
        return self._pacing_gain

    @property
    def phase(self) -> str:
        """Current pacing phase."""
        return self._phase

    @property
    def rate_history(self) -> list:
        """Complete history of computed pacing rates."""
        return list(self._rate_history)

    @property
    def phase_transitions(self) -> list:
        """Record of all phase transitions."""
        return list(self._phase_transitions)

    def get_summary(self) -> dict:
        """Return pacer state summary."""
        return {
            "pacing_rate": self._last_pacing_rate,
            "pacing_gain": self._pacing_gain,
            "phase": self._phase,
            "cwnd": self._cwnd,
            "transitions": len(self._phase_transitions),
        }
