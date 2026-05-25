#!/bin/bash
set -e

cd /app
python -m runtime.run_analysis

cd /tests
uv run --with pytest pytest test_lattice_flow.py -v
