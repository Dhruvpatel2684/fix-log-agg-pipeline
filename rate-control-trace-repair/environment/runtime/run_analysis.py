"""Entry point for congestion control trace replay analysis.

Loads configuration, reads trace files, replays each trace through the
congestion control stack, and produces output reports.
"""

import configparser
import os
import sys

from runtime.estimator import CombinedEstimator
from runtime.controller import CUBICController, CongestionState
from runtime.detector import CongestionDetector
from runtime.pacer import PacingController, PacingPhase
from runtime.reporter import AnalysisReport


def load_config(config_path: str = None) -> configparser.ConfigParser:
    """Load analysis configuration from INI file."""
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "config.ini")
    config = configparser.ConfigParser()
    config.read(config_path)
    return config


def parse_trace_line(line: str) -> dict:
    """Parse a single pipe-delimited trace line.

    Format: timestamp_ms|event_type|seq_num|bytes_acked|rtt_sample_ms|extra
    """
    parts = line.strip().split('|')
    if len(parts) < 6:
        return None
    return {
        'timestamp_ms': float(parts[0]),
        'event_type': parts[1].strip(),
        'seq_num': int(parts[2]),
        'bytes_acked': int(parts[3]),
        'rtt_sample_ms': float(parts[4]),
        'extra': parts[5].strip() if len(parts) > 5 else '',
    }


def load_trace(trace_path: str) -> list:
    """Load and parse a trace file."""
    events = []
    with open(trace_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            event = parse_trace_line(line)
            if event:
                events.append(event)
    return events


def replay_trace(events: list, config: configparser.ConfigParser) -> dict:
    """Replay a trace through the congestion control stack.

    Returns a dictionary of computed metrics for this trace.
    """
    # Initialize components from config
    estimator = CombinedEstimator(
        alpha=config.getfloat('estimation', 'ewma_alpha'),
        min_rtt_window_ms=config.getint('estimation', 'min_rtt_window_ms'),
        bw_filter_len=config.getint('estimation', 'bw_filter_len'),
    )
    controller = CUBICController(
        C=config.getfloat('cubic', 'C'),
        beta=config.getfloat('cubic', 'beta'),
        initial_cwnd=config.getint('cubic', 'initial_cwnd'),
        max_cwnd=config.getint('cubic', 'max_cwnd'),
    )
    detector = CongestionDetector(
        loss_window_ms=config.getfloat('detection', 'loss_window_ms'),
        timeout_multiplier=config.getfloat('detection', 'timeout_multiplier'),
    )
    pacer = PacingController(
        default_gain=config.getfloat('pacing', 'default_gain'),
        probe_gain=config.getfloat('pacing', 'probe_gain'),
        drain_gain=config.getfloat('pacing', 'drain_gain'),
    )

    total_events = 0
    pre_loss_cwnd = None
    cruise_rate_before_probe = 0.0
    max_probe_rate = 0.0
    in_probe = False
    immediate_post_loss_cwnd = None

    for event in events:
        total_events += 1
        ts = event['timestamp_ms']
        etype = event['event_type']
        seq = event['seq_num']
        bytes_acked = event['bytes_acked']
        rtt_ms = event['rtt_sample_ms']

        if etype == 'ACK':
            estimator.process_ack(ts, bytes_acked, rtt_ms)
            detector.on_ack(ts, seq)
            controller.on_ack(ts, bytes_acked)
            # Exit recovery after processing ACKs
            if controller.state == CongestionState.RECOVERY:
                controller.exit_recovery(ts)

        elif etype == 'LOSS':
            is_new = detector.on_loss(ts, seq)
            if is_new:
                pre_loss_cwnd = controller.cwnd
                controller.on_loss(ts)
                immediate_post_loss_cwnd = controller.cwnd

        elif etype == 'TIMEOUT':
            detector.on_timeout(ts)
            controller.on_timeout(ts)

        elif etype == 'PROBE_START':
            # Record cruise rate just before entering probe
            if pacer.current_rate > 0:
                cruise_rate_before_probe = pacer.current_rate
            pacer.set_phase(PacingPhase.PROBE_UP, ts)
            in_probe = True

        elif etype == 'PROBE_END':
            pacer.set_phase(PacingPhase.CRUISE, ts)
            in_probe = False

        # Update pacing rate after each event
        if estimator.srtt > 0:
            rate = pacer.compute_pacing_rate(controller.cwnd, estimator.srtt)
            if in_probe and rate > max_probe_rate:
                max_probe_rate = rate

    # Compile results
    post_loss_cwnd = controller.cwnd
    beta_ratio = 0.0
    if pre_loss_cwnd and pre_loss_cwnd > 0:
        beta_ratio = post_loss_cwnd / pre_loss_cwnd

    # Compute probe gain ratio (max probe rate vs pre-probe cruise rate)
    probe_gain_ratio = 0.0
    if cruise_rate_before_probe > 0 and max_probe_rate > 0:
        probe_gain_ratio = max_probe_rate / cruise_rate_before_probe

    # Immediate reduction ratio at loss point
    loss_reduction_ratio = 0.0
    if pre_loss_cwnd and pre_loss_cwnd > 0 and immediate_post_loss_cwnd is not None:
        loss_reduction_ratio = immediate_post_loss_cwnd / pre_loss_cwnd

    result = {
        'cwnd_final': controller.cwnd,
        'bw_estimate': estimator.bandwidth,
        'loss_rate': detector.get_loss_rate(),
        'pacing_rate': pacer.current_rate,
        'srtt': estimator.srtt,
        'min_rtt': estimator.min_rtt,
        'total_events': total_events,
        'ack_count': controller.ack_count,
        'loss_count': controller.loss_count,
        'congestion_events': detector.congestion_event_count,
        'pacing_gain': pacer.current_gain,
        'beta_ratio': beta_ratio,
        'pre_loss_cwnd': pre_loss_cwnd if pre_loss_cwnd else 0,
        'post_loss_cwnd': post_loss_cwnd,
        'probe_gain_ratio': probe_gain_ratio,
        'cruise_rate_before_probe': cruise_rate_before_probe,
        'max_probe_rate': max_probe_rate,
        'loss_reduction_ratio': loss_reduction_ratio,
    }
    return result


def main():
    """Main entry point: load config, replay traces, write reports."""
    config = load_config()

    # Determine trace directory
    data_dir = os.path.join(os.path.dirname(__file__), "data")

    # Get active traces from config
    active_traces = config.get('analysis', 'active_traces').split(',')
    active_traces = [t.strip() for t in active_traces]

    report = AnalysisReport(
        output_dir=config.get('analysis', 'output_dir')
    )

    for trace_name in active_traces:
        trace_path = os.path.join(data_dir, f"{trace_name}.log")
        if not os.path.exists(trace_path):
            print(f"Warning: trace file not found: {trace_path}")
            continue

        events = load_trace(trace_path)
        result = replay_trace(events, config)
        report.add_trace_result(trace_name, result)
        print(f"Processed {trace_name}: {len(events)} events, "
              f"cwnd={result['cwnd_final']}, bw={result['bw_estimate']:.2f}, "
              f"loss={result['loss_rate']:.4f}")

    report.write_output()
    print(f"\nAnalysis complete. {report.trace_count} traces processed.")
    print(f"Output written to: {config.get('analysis', 'output_dir')}")


if __name__ == "__main__":
    main()
