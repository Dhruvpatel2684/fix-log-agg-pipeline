#!/bin/bash
set -e
cd /app
python3 -m runtime.run_analysis
mkdir -p /logs/verifier
set +e
uv run --with pytest pytest /tests/test_lattice_flow.py -v 2>&1 | tee /logs/verifier/output.log
TEST_EXIT=${PIPESTATUS[0]}
set -e
if [ $TEST_EXIT -eq 0 ]; then echo "1" > /logs/verifier/reward.txt; else echo "0" > /logs/verifier/reward.txt; fi
exit $TEST_EXIT
