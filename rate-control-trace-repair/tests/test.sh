#!/bin/bash
set -e

cd /app

# Run the analysis first to generate output
python -m runtime.run_analysis > /dev/null 2>&1 || true

# Run the test suite
python -m pytest /tests/test_rate_control.py -v --tb=short 2>&1
