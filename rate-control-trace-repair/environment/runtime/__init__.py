# Harbor Terminal-Bench: Rate Control Trace Repair
# Network packet trace analysis with CUBIC congestion control simulation
"""
This package implements a network trace replay engine that processes
packet acknowledgment traces and simulates TCP CUBIC congestion control
behavior to produce bandwidth estimation, congestion window evolution,
and link utilization metrics.

Modules:
    estimator   - RTT and bandwidth estimation (EWMA, Jacobson/Karels)
    controller  - CUBIC congestion control state machine
    detector    - Loss detection and RTO computation
    pacer       - Token bucket pacing engine
    reporter    - Statistics aggregation and output generation
    run_analysis - Entry point and trace replay orchestration
"""

__version__ = "2.4.1"
__author__ = "Network Systems Lab"
