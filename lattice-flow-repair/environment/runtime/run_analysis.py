"""
Entry point for abstract interpretation analysis.

Loads program trace specifications, runs the interval domain
analyzer on each, and produces structured output reports.
"""

import json
import os
import sys
import configparser

sys.path.insert(0, "/app")

from runtime.analyzer import TraceAnalyzer


def main():
    config_path = "/app/runtime/config.ini"
    data_dir = "/app/runtime/data"

    config = configparser.ConfigParser()
    config.read(config_path)

    output_dir = config.get("analysis", "output_dir")
    active_traces = [t.strip() for t in config.get("analysis", "active_traces").split(",")]

    os.makedirs(output_dir, exist_ok=True)

    analyzer = TraceAnalyzer(config_path)

    results = {}
    for trace_name in active_traces:
        trace_path = os.path.join(data_dir, f"{trace_name}.json")
        if not os.path.exists(trace_path):
            continue
        with open(trace_path) as f:
            trace = json.load(f)
        result = analyzer.analyze_trace(trace)
        results[trace_name] = {
            "trace_id": trace_name,
            "description": trace.get("description", ""),
            "variables": result
        }

    # Write detailed results
    analysis_path = os.path.join(output_dir, "analysis_results.json")
    with open(analysis_path, "w") as f:
        json.dump(results, f, indent=2)

    # Write summary
    summary = {
        "total_traces": len(results),
        "trace_ids": list(results.keys()),
        "variables_per_trace": {
            tid: list(r["variables"].keys()) for tid, r in results.items()
        }
    }
    summary_path = os.path.join(output_dir, "summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Analysis complete. Results written to {output_dir}")
    for tid, r in results.items():
        print(f"  {tid}: {len(r['variables'])} variables analyzed")


if __name__ == "__main__":
    main()
