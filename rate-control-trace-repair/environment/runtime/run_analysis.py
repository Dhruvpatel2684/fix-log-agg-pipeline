"""
Trace Replay Entry Point

Orchestrates the full analysis pipeline:
    1. Parse configuration
    2. Load trace data files
    3. Replay each trace through the congestion control stack
    4. Aggregate results and generate report

Trace format (pipe-delimited):
    timestamp_ms|event_type|bytes_acked|rtt_ms|seq_num|flags

Event types:
    ACK  - Acknowledgment received
    LOSS - Packet loss detected (timeout or triple-dupack)
    SEND - Packet transmitted

The replay engine processes events chronologically, feeding them
through the estimator → controller → detector → pacer pipeline.
"""

import os
import sys
import json
import configparser
from typing import Dict, List, Tuple, Optional

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from runtime.estimator import CombinedEstimator
from runtime.controller import CUBICController
from runtime.detector import LossDetector
from runtime.pacer import PacingEngine
from runtime.reporter import ReportGenerator


def load_config(config_path: str) -> Dict:
    """
    Load and parse INI configuration file.
    
    Args:
        config_path: Path to config.ini
        
    Returns:
        Nested dictionary of configuration sections
    """
    parser = configparser.ConfigParser()
    parser.read(config_path)

    config = {}
    for section in parser.sections():
        config[section] = {}
        for key, value in parser.items(section):
            # Try numeric conversion
            try:
                if '.' in value:
                    config[section][key] = float(value)
                else:
                    config[section][key] = int(value)
            except ValueError:
                config[section][key] = value

    return config


def parse_trace_file(filepath: str) -> List[Dict]:
    """
    Parse a pipe-delimited trace file into event records.
    
    Skips comment lines (starting with #) and blank lines.
    
    Args:
        filepath: Path to trace log file
        
    Returns:
        List of event dictionaries
    """
    events = []
    
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parts = line.split('|')
            if len(parts) < 6:
                continue

            try:
                event = {
                    "timestamp_ms": float(parts[0]),
                    "event_type": parts[1].strip(),
                    "bytes_acked": int(parts[2]),
                    "rtt_ms": float(parts[3]),
                    "seq_num": int(parts[4]),
                    "flags": parts[5].strip()
                }
                events.append(event)
            except (ValueError, IndexError):
                continue

    return events


def replay_trace(trace_name: str, events: List[Dict],
                 config: Dict) -> Dict:
    """
    Replay a single trace through the congestion control stack.
    
    Processes each event through the appropriate module based on
    event type, tracking state evolution across the full pipeline.
    
    Args:
        trace_name: Identifier for this trace
        events: Parsed event list
        config: Full configuration dictionary
        
    Returns:
        Per-trace results dictionary
    """
    # Initialize pipeline components
    estimator = CombinedEstimator(config.get("estimation", {}))
    controller = CUBICController(config.get("cubic", {}))
    detector = LossDetector(config.get("detection", {}))
    pacer = PacingEngine(config.get("pacing", {}))

    results = {
        "trace": trace_name,
        "events_processed": 0,
        "acks_processed": 0,
        "losses_detected": 0,
        "sends_processed": 0,
        "final_cwnd": 0.0,
        "final_srtt": 0.0,
        "max_cwnd": 0.0,
        "delivery_rates": [],
        "cwnd_history": [],
        "srtt_history": [],
    }

    seq_counter = 0
    
    for event in events:
        ts = event["timestamp_ms"]
        etype = event["event_type"]
        results["events_processed"] += 1

        if etype == "ACK":
            bytes_acked = event["bytes_acked"]
            rtt_ms = event["rtt_ms"]
            seq_num = event["seq_num"]

            # Process through estimator
            estimates = estimator.process_ack(ts, rtt_ms, bytes_acked)
            
            # Update controller
            min_rtt = estimates["min_rtt"] if estimates["min_rtt"] else rtt_ms
            cwnd = controller.on_ack(ts, bytes_acked, rtt_ms, min_rtt)
            
            # Check for losses via detector
            losses = detector.on_ack(
                ts, seq_num, estimates["srtt"], estimates["rttvar"]
            )
            
            # Handle detected losses
            for lost_seq, loss_type in losses:
                controller.on_loss(ts, lost_seq)
                results["losses_detected"] += 1
            
            # Update pacer with new rate
            pacer.update_rate(cwnd, estimates["srtt"], ts)
            
            # Record state
            results["acks_processed"] += 1
            results["delivery_rates"].append(estimates["delivery_rate"])
            results["cwnd_history"].append(cwnd)
            results["srtt_history"].append(estimates["srtt"])
            results["max_cwnd"] = max(results["max_cwnd"], cwnd)

        elif etype == "LOSS":
            seq_num = event["seq_num"]
            cwnd = controller.on_loss(ts, seq_num)
            results["losses_detected"] += 1
            results["cwnd_history"].append(cwnd)

        elif etype == "SEND":
            seq_num = event["seq_num"]
            bytes_sent = event["bytes_acked"]  # Reuse field for send size
            detector.on_send(ts, seq_num, bytes_sent)
            results["sends_processed"] += 1
            seq_counter = max(seq_counter, seq_num)

    # Record final state
    results["final_cwnd"] = controller.cwnd
    results["final_srtt"] = estimator.rtt_estimator.srtt
    results["controller_summary"] = controller.get_state_summary()
    results["detection_summary"] = detector.get_loss_summary()
    results["pacing_summary"] = pacer.get_pacing_stats()

    return results


def run_full_analysis(config_path: str = None) -> Dict:
    """
    Execute the complete trace analysis pipeline.
    
    Loads configuration, processes all configured traces, and
    generates the aggregated report.
    
    Args:
        config_path: Path to config.ini (default: adjacent to this file)
        
    Returns:
        Complete analysis report dictionary
    """
    # Determine paths
    runtime_dir = os.path.dirname(os.path.abspath(__file__))
    if config_path is None:
        config_path = os.path.join(runtime_dir, "config.ini")
    
    data_dir = os.path.join(runtime_dir, "data")

    # Load configuration
    config = load_config(config_path)

    # Initialize reporter
    reporter = ReportGenerator(config.get("reporting", {}))

    # Get active traces
    active_traces_str = config.get("analysis", {}).get("active_traces", "")
    if isinstance(active_traces_str, str):
        trace_names = [t.strip() for t in active_traces_str.split(",") if t.strip()]
    else:
        trace_names = []

    all_results = {}

    for trace_name in trace_names:
        trace_path = os.path.join(data_dir, f"{trace_name}.log")
        
        if not os.path.exists(trace_path):
            continue

        # Parse and replay trace
        events = parse_trace_file(trace_path)
        if not events:
            continue

        results = replay_trace(trace_name, events, config)
        all_results[trace_name] = results

        # Feed results to reporter
        flow = reporter.add_flow(trace_name)
        for event in events:
            if event["event_type"] == "ACK":
                flow.record_ack(event["timestamp_ms"], event["bytes_acked"])
                reporter.add_rtt_sample(event["rtt_ms"])
            elif event["event_type"] == "LOSS":
                flow.record_loss(event["timestamp_ms"], event.get("bytes_acked", 0))

        reporter.add_controller_summary(results["controller_summary"])
        reporter.add_detection_summary(results["detection_summary"])
        reporter.add_pacing_summary(results["pacing_summary"])

    # Generate and write report
    report = reporter.generate_report()
    report["trace_results"] = {
        name: {
            k: v for k, v in res.items() 
            if k not in ("delivery_rates", "cwnd_history", "srtt_history")
        }
        for name, res in all_results.items()
    }
    
    # Add condensed time series
    report["time_series"] = {}
    for name, res in all_results.items():
        dr = res.get("delivery_rates", [])
        cw = res.get("cwnd_history", [])
        sr = res.get("srtt_history", [])
        report["time_series"][name] = {
            "delivery_rate_samples": dr[-50:] if len(dr) > 50 else dr,
            "cwnd_samples": cw[-50:] if len(cw) > 50 else cw,
            "srtt_samples": sr[-50:] if len(sr) > 50 else sr,
        }

    output_path = reporter.write_report(report)
    report["_output_path"] = output_path

    return report


if __name__ == "__main__":
    report = run_full_analysis()
    print(json.dumps(report, indent=2, default=str))
