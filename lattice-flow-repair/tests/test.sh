#!/bin/bash
set -e

cp -r /app/runtime /tests/runtime 2>/dev/null || true
cd /tests
uv run --with pytest pytest /tests/test_lattice_flow.py -v
