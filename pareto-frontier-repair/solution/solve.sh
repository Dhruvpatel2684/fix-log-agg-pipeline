#!/bin/bash
set -e
# Run the broken engine to generate initial output
python3 /app/runtime/pareto_engine.py
# Re-process with corrected normalization, dominance, and ranking
python3 /solution/repair_pareto.py
