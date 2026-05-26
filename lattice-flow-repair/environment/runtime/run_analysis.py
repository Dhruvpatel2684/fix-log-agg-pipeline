"""
Analysis Runner
================
Entry point for the anomaly correlation analysis. Loads trace data,
runs the correlation engine, computes evaluation metrics, and produces
aggregated reports.
"""

from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from typing import Dict, List

from .graph import ServiceDependencyGraph
from .events import EventTimeline, AnomalyEvent, GroundTruthLabels, load_events_from_json
from .correlator import CorrelationEngine, correlate_trace
from .aggregator import CorrelationAggregator, AggregationReport
from .metrics import MetricsEvaluator, EvaluationReport, quick_evaluate


DEFAULT_DATA_DIR = "/app/runtime/data"
DEFAULT_WINDOW_MS = 30000
DEFAULT_CONFIDENCE = 0.6


def load_trace_file(filepath: str) -> Dict:
    """Load a trace file and return parsed JSON data."""
    with open(filepath, "r") as f:
        return json.load(f)


def build_graph_from_trace(trace_data: Dict) -> ServiceDependencyGraph:
    """Build a ServiceDependencyGraph from trace data."""
    return ServiceDependencyGraph.from_dict(trace_data["graph"])


def build_timeline_from_trace(trace_data: Dict) -> EventTimeline:
    """Build an EventTimeline from trace data."""
    timeline = EventTimeline()
    for event_data in trace_data.get("events", []):
        event = AnomalyEvent.from_dict(event_data)
        timeline.add(event)
    return timeline


def build_ground_truth_from_trace(trace_data: Dict) -> GroundTruthLabels:
    """Build GroundTruthLabels from trace data."""
    return GroundTruthLabels.from_list(trace_data.get("ground_truth", []))


def run_single_trace(
    filepath: str,
    window_ms: int = DEFAULT_WINDOW_MS,
    confidence_threshold: float = DEFAULT_CONFIDENCE,
) -> Dict:
    """
    Run full analysis on a single trace file.
    Returns dict with results, metrics, and aggregation report.
    """
    trace_data = load_trace_file(filepath)
    graph = build_graph_from_trace(trace_data)
    timeline = build_timeline_from_trace(trace_data)
    ground_truth = build_ground_truth_from_trace(trace_data)

    # Run correlation
    engine = CorrelationEngine(
        graph=graph,
        window_ms=window_ms,
        confidence_threshold=confidence_threshold,
    )
    results = engine.correlate_events(timeline)

    # Evaluate
    evaluator = MetricsEvaluator(ground_truth)
    eval_report = evaluator.evaluate(results)

    # Aggregate
    aggregator = CorrelationAggregator(graph, timeline)
    agg_report = aggregator.aggregate(results)

    return {
        "trace_file": os.path.basename(filepath),
        "event_count": timeline.count(),
        "pair_count": len(results),
        "causal_count": agg_report.causal_pairs,
        "independent_count": agg_report.independent_pairs,
        "precision": eval_report.precision,
        "recall": eval_report.recall,
        "f1_score": eval_report.f1_score,
        "chain_count": len(agg_report.causal_chains),
        "max_chain_length": agg_report.max_chain_length,
    }


def run_all_traces(
    data_dir: str = DEFAULT_DATA_DIR,
    window_ms: int = DEFAULT_WINDOW_MS,
    confidence_threshold: float = DEFAULT_CONFIDENCE,
) -> List[Dict]:
    """Run analysis on all trace files in the data directory."""
    results = []
    data_path = Path(data_dir)

    if not data_path.exists():
        print(f"Data directory not found: {data_dir}", file=sys.stderr)
        return results

    trace_files = sorted(data_path.glob("trace_*.json"))
    if not trace_files:
        print(f"No trace files found in: {data_dir}", file=sys.stderr)
        return results

    for trace_file in trace_files:
        try:
            result = run_single_trace(
                str(trace_file),
                window_ms=window_ms,
                confidence_threshold=confidence_threshold,
            )
            results.append(result)
        except Exception as e:
            print(f"Error processing {trace_file.name}: {e}", file=sys.stderr)
            results.append({"trace_file": trace_file.name, "error": str(e)})

    return results


def print_summary(results: List[Dict]) -> None:
    """Print a summary table of results."""
    print("\n" + "=" * 70)
    print("ANOMALY CORRELATION ANALYSIS SUMMARY")
    print("=" * 70)
    print(f"{'Trace':<20} {'Events':<8} {'Pairs':<8} {'Prec':<8} {'Recall':<8} {'F1':<8}")
    print("-" * 70)

    for r in results:
        if "error" in r:
            print(f"{r['trace_file']:<20} ERROR: {r['error']}")
        else:
            print(
                f"{r['trace_file']:<20} "
                f"{r['event_count']:<8} "
                f"{r['pair_count']:<8} "
                f"{r['precision']:<8.4f} "
                f"{r['recall']:<8.4f} "
                f"{r['f1_score']:<8.4f}"
            )

    print("=" * 70)

    # Aggregate metrics
    valid = [r for r in results if "error" not in r]
    if valid:
        avg_prec = sum(r["precision"] for r in valid) / len(valid)
        avg_recall = sum(r["recall"] for r in valid) / len(valid)
        avg_f1 = sum(r["f1_score"] for r in valid) / len(valid)
        print(f"{'AVERAGE':<20} {'':8} {'':8} {avg_prec:<8.4f} {avg_recall:<8.4f} {avg_f1:<8.4f}")
    print()


def main():
    """Main entry point."""
    data_dir = os.environ.get("DATA_DIR", DEFAULT_DATA_DIR)
    window_ms = int(os.environ.get("WINDOW_MS", str(DEFAULT_WINDOW_MS)))
    confidence = float(os.environ.get("CONFIDENCE", str(DEFAULT_CONFIDENCE)))

    results = run_all_traces(
        data_dir=data_dir,
        window_ms=window_ms,
        confidence_threshold=confidence,
    )

    print_summary(results)

    # Output JSON for programmatic consumption
    output = {
        "traces": results,
        "config": {
            "data_dir": data_dir,
            "window_ms": window_ms,
            "confidence_threshold": confidence,
        },
    }
    print(json.dumps(output, indent=2))

    return results


if __name__ == "__main__":
    main()
