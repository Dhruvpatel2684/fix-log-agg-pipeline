#!/bin/bash
set -e
# Run the broken engine to generate initial output
python3 /app/runtime/mac_engine.py
# Re-process with corrected chain advancement, non-conflicting detection, and verification order
python3 /solution/repair_chain.py
