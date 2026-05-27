"""
Statistics Aggregation and Report Generation Module

Computes summary statistics from the trace replay including:
    - Throughput and goodput measurements
    - Link utilization ratio
    - RTT statistics (mean, P50, P95, P99)
    - Loss rate and recovery efficiency
    - Jain's fairness index for multi-flow scenarios
    - Congestion window dynamics summary

Output is written as JSON for downstream processing and visualization.

References:
    Jain et al. - "A Quantitative Measure of Fairness" (1984)
    RFC 3148 - A Framework for Defining Empirical Bulk Transfer Capacity Metrics
"""

import json
import math
import os
from typing import Dict, List, Optional, Tuple


class RTTStatistics:
    """
    Compute percentile and aggregate RTT statistics.
    
    Maintains a sorted collection of RTT samples and provides
    efficient percentile queries and moment computation.
    """

    def __init__(self):
        """Initialize empty RTT statistics collector."""
        self._samples: List[float] = []
        self._sorted = False
        self._sum: float = 0.0
        self._sum_sq: float = 0.0
        self._count: int = 0

    def add_sample(self, rtt_ms: float):
        """Add an RTT sample."""
        self._samples.append(rtt_ms)
        self._sum += rtt_ms
        self._sum_sq += rtt_ms * rtt_ms
        self._count += 1
        self._sorted = False

    def _ensure_sorted(self):
        """Sort samples if needed for percentile queries."""
        if not self._sorted:
            self._samples.sort()
            self._sorted = True

    @property
    def mean(self) -> float:
        """Arithmetic mean RTT."""
        return self._sum / self._count if self._count > 0 else 0.0

    @property
    def std(self) -> float:
        """Standard deviation of RTT samples."""
        if self._count < 2:
            return 0.0
        variance = (self._sum_sq / self._count) - (self.mean ** 2)
        return math.sqrt(max(variance, 0.0))

    def percentile(self, p: float) -> float:
        """
        Compute the p-th percentile RTT.
        
        Args:
            p: Percentile value (0-100)
            
        Returns:
            RTT value at the given percentile
        """
        if not self._samples:
            return 0.0
        self._ensure_sorted()
        idx = int(len(self._samples) * p / 100.0)
        idx = min(idx, len(self._samples) - 1)
        return self._samples[idx]

    @property
    def count(self) -> int:
        """Number of samples collected."""
        return self._count

    def get_summary(self) -> Dict[str, float]:
        """Get complete RTT statistics summary."""
        return {
            "mean_ms": self.mean,
            "std_ms": self.std,
            "p50_ms": self.percentile(50),
            "p95_ms": self.percentile(95),
            "p99_ms": self.percentile(99),
            "min_ms": min(self._samples) if self._samples else 0.0,
            "max_ms": max(self._samples) if self._samples else 0.0,
            "count": self._count
        }


class FlowMetrics:
    """
    Per-flow throughput and delivery metrics.
    
    Tracks bytes delivered, time intervals, and computes
    throughput and goodput statistics for a single flow.
    """

    def __init__(self, flow_id: str):
        """
        Initialize flow metrics.
        
        Args:
            flow_id: Identifier for this flow (trace name)
        """
        self._flow_id = flow_id
        self._total_bytes_acked: int = 0
        self._retransmitted_bytes: int = 0
        self._start_time_ms: Optional[float] = None
        self._end_time_ms: Optional[float] = None
        self._events_processed: int = 0
        self._loss_count: int = 0
        self._ack_count: int = 0

    def record_ack(self, timestamp_ms: float, bytes_acked: int):
        """Record a successful ACK event."""
        if self._start_time_ms is None:
            self._start_time_ms = timestamp_ms
        self._end_time_ms = timestamp_ms
        self._total_bytes_acked += bytes_acked
        self._ack_count += 1
        self._events_processed += 1

    def record_loss(self, timestamp_ms: float, bytes_lost: int):
        """Record a loss event."""
        if self._start_time_ms is None:
            self._start_time_ms = timestamp_ms
        self._end_time_ms = timestamp_ms
        self._retransmitted_bytes += bytes_lost
        self._loss_count += 1
        self._events_processed += 1

    @property
    def elapsed_sec(self) -> float:
        """Total elapsed time in seconds."""
        if self._start_time_ms is None or self._end_time_ms is None:
            return 0.0
        return max((self._end_time_ms - self._start_time_ms) / 1000.0, 0.001)

    @property
    def throughput_bps(self) -> float:
        """Raw throughput in bytes per second."""
        return self._total_bytes_acked / self.elapsed_sec

    @property
    def goodput_bps(self) -> float:
        """Goodput (useful throughput) excluding retransmissions."""
        useful = max(self._total_bytes_acked - self._retransmitted_bytes, 0)
        return useful / self.elapsed_sec

    @property
    def loss_rate(self) -> float:
        """Fraction of events that were losses."""
        total = self._ack_count + self._loss_count
        return self._loss_count / total if total > 0 else 0.0

    def get_summary(self) -> Dict:
        """Get flow metrics summary."""
        return {
            "flow_id": self._flow_id,
            "total_bytes": self._total_bytes_acked,
            "retransmitted_bytes": self._retransmitted_bytes,
            "elapsed_sec": self.elapsed_sec,
            "throughput_Bps": self.throughput_bps,
            "goodput_Bps": self.goodput_bps,
            "loss_rate": self.loss_rate,
            "ack_count": self._ack_count,
            "loss_count": self._loss_count
        }


class ReportGenerator:
    """
    Aggregated report generation across all analyzed traces.
    
    Combines per-flow metrics with controller state to produce
    comprehensive analysis output including utilization metrics
    and fairness indices.
    """

    def __init__(self, config: Dict):
        """
        Initialize report generator.
        
        Args:
            config: Configuration with:
                - link_rate_mbps: Configured link capacity in megabits/sec
                - output_dir: Directory for report output
        """
        self._link_rate_mbps = config.get("link_rate_mbps", 100.0)
        self._output_dir = config.get("output_dir", "./output")
        self._flows: Dict[str, FlowMetrics] = {}
        self._rtt_stats = RTTStatistics()
        self._controller_summaries: List[Dict] = []
        self._detection_summaries: List[Dict] = []
        self._pacing_summaries: List[Dict] = []

    def add_flow(self, flow_id: str) -> FlowMetrics:
        """Register a new flow for tracking."""
        flow = FlowMetrics(flow_id)
        self._flows[flow_id] = flow
        return flow

    def add_rtt_sample(self, rtt_ms: float):
        """Add an RTT observation to global statistics."""
        self._rtt_stats.add_sample(rtt_ms)

    def add_controller_summary(self, summary: Dict):
        """Record controller state summary."""
        self._controller_summaries.append(summary)

    def add_detection_summary(self, summary: Dict):
        """Record loss detection summary."""
        self._detection_summaries.append(summary)

    def add_pacing_summary(self, summary: Dict):
        """Record pacing engine summary."""
        self._pacing_summaries.append(summary)

    def compute_utilization(self) -> float:
        """
        Compute overall link utilization.
        
        Calculates the fraction of link capacity actually used,
        based on total bytes delivered and link capacity.
        
        Returns:
            Utilization ratio in [0, 1]
        """
        total_bytes = sum(f._total_bytes_acked for f in self._flows.values())
        total_elapsed_sec = max(
            max((f.elapsed_sec for f in self._flows.values()), default=0.001),
            0.001
        )

        # Link utilization: fraction of available capacity used
        # Capacity in bytes/sec derived from configured link rate in Mbps
        capacity_bytes_sec = self._link_rate_mbps * 1000000
        utilization = total_bytes / (capacity_bytes_sec * total_elapsed_sec)

        return min(utilization, 1.0)

    def compute_fairness(self) -> float:
        """
        Compute Jain's fairness index across all flows.
        
        Jain's index measures how fairly bandwidth is distributed:
            F = (sum(x_i))^2 / (n * sum(x_i^2))
        
        Ranges from 1/n (maximally unfair) to 1 (perfectly fair).
        
        Returns:
            Fairness index in [1/n, 1]
        """
        throughputs = [f.throughput_bps for f in self._flows.values()
                       if f.throughput_bps > 0]
        
        if len(throughputs) < 2:
            return 1.0

        n = len(throughputs)
        sum_x = sum(throughputs)
        sum_x2 = sum(x * x for x in throughputs)

        if sum_x2 == 0:
            return 1.0

        return (sum_x ** 2) / (n * sum_x2)

    def generate_report(self) -> Dict:
        """
        Generate the complete analysis report.
        
        Combines all metrics into a single report dictionary suitable
        for JSON serialization and downstream processing.
        
        Returns:
            Complete report dictionary
        """
        utilization = self.compute_utilization()
        fairness = self.compute_fairness()

        report = {
            "version": "2.4.1",
            "summary": {
                "total_flows": len(self._flows),
                "link_utilization": utilization,
                "fairness_index": fairness,
                "link_rate_mbps": self._link_rate_mbps,
            },
            "rtt_statistics": self._rtt_stats.get_summary(),
            "flows": {
                fid: flow.get_summary() 
                for fid, flow in self._flows.items()
            },
            "controller": self._controller_summaries,
            "detection": self._detection_summaries,
            "pacing": self._pacing_summaries
        }

        return report

    def write_report(self, report: Dict, filename: str = "analysis_report.json"):
        """
        Write report to output directory as JSON.
        
        Creates output directory if it doesn't exist.
        
        Args:
            report: Report dictionary to serialize
            filename: Output filename
        """
        os.makedirs(self._output_dir, exist_ok=True)
        output_path = os.path.join(self._output_dir, filename)

        with open(output_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        return output_path
