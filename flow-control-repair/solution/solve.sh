#!/bin/bash
set -e
# Run the broken engine to generate initial output
python3 /app/runtime/flow_engine.py
# Re-process with corrected window advancement, contention-free detection, and scheduling
python3 /solution/repair_flow.py
