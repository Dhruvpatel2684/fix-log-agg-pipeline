#!/bin/bash
cd /app
python3 /solution/repair_lattice_flow.py
python3 -m runtime.run_analysis
