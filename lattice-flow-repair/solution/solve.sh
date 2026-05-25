#!/bin/bash
set -e

cd /app
python /solution/repair_lattice_flow.py
python -m runtime.run_analysis
