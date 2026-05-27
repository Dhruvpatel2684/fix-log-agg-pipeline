"""Output generation module for trace analysis results.

Formats and writes analysis results including per-trace statistics
and aggregate metrics to JSON output files.
"""

import json
import os


class AnalysisReport:
    """Collects and formats analysis results from trace replay."""

    def __init__(self, output_dir: str = "/app/runtime/output"):
        self._output_dir = output_dir
        self._trace_results: dict = {}
        self._aggregate_metrics: dict = {}

    def add_trace_result(self, trace_name: str, result: dict):
        """Record results for a single trace replay.

        Args:
            trace_name: Identifier for the trace (e.g., 'trace_alpha').
            result: Dictionary containing computed metrics.
        """
        self._trace_results[trace_name] = result

    def compute_aggregate(self):
        """Compute aggregate metrics across all traces."""
        if not self._trace_results:
            return

        bw_values = []
        loss_values = []
        cwnd_values = []
        pacing_values = []

        for name, result in self._trace_results.items():
            bw_values.append(result.get('bw_estimate', 0.0))
            loss_values.append(result.get('loss_rate', 0.0))
            cwnd_values.append(result.get('cwnd_final', 0))
            pacing_values.append(result.get('pacing_rate', 0.0))

        self._aggregate_metrics = {
            'trace_count': len(self._trace_results),
            'avg_bandwidth': sum(bw_values) / len(bw_values) if bw_values else 0.0,
            'avg_loss_rate': sum(loss_values) / len(loss_values) if loss_values else 0.0,
            'avg_cwnd': sum(cwnd_values) / len(cwnd_values) if cwnd_values else 0.0,
            'avg_pacing_rate': sum(pacing_values) / len(pacing_values) if pacing_values else 0.0,
            'jains_fairness': self._compute_jains_index(bw_values),
        }

    def _compute_jains_index(self, values: list) -> float:
        """Compute Jain's fairness index for a set of values.

        J(x1...xn) = (sum(xi))^2 / (n * sum(xi^2))
        """
        if not values or all(v == 0 for v in values):
            return 0.0
        n = len(values)
        sum_x = sum(values)
        sum_x2 = sum(v * v for v in values)
        if sum_x2 == 0:
            return 0.0
        return (sum_x ** 2) / (n * sum_x2)

    def write_output(self):
        """Write results to output directory."""
        os.makedirs(self._output_dir, exist_ok=True)

        # Write per-trace results
        for trace_name, result in self._trace_results.items():
            output_path = os.path.join(self._output_dir, f"{trace_name}_result.json")
            with open(output_path, 'w') as f:
                json.dump(result, f, indent=2)

        # Write aggregate report
        self.compute_aggregate()
        aggregate_path = os.path.join(self._output_dir, "aggregate_report.json")
        with open(aggregate_path, 'w') as f:
            json.dump({
                'trace_results': self._trace_results,
                'aggregate': self._aggregate_metrics,
            }, f, indent=2)

    @property
    def trace_results(self) -> dict:
        """All per-trace results."""
        return dict(self._trace_results)

    @property
    def aggregate_metrics(self) -> dict:
        """Aggregate metrics across traces."""
        return dict(self._aggregate_metrics)

    @property
    def trace_count(self) -> int:
        """Number of traces processed."""
        return len(self._trace_results)
