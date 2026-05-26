#!/bin/bash
set -euo pipefail
mkdir -p /logs/verifier
if [ ! -f /app/runtime/pareto_state.jsonl ]; then
    python3 /app/runtime/pareto_engine.py
fi
set +e
uv run --with pytest pytest -v /tests/test_pareto.py
TEST_EXIT=$?
set -e
if [ "$TEST_EXIT" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
cat /logs/verifier/reward.txt
exit "$TEST_EXIT"
