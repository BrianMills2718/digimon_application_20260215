#!/bin/bash
# Overnight benchmark: build graph + run 200-question agent benchmark
# Expected: ~3-4 hours, ~16-20 USD (mostly GEMINI_API_KEY)
#
# Usage: nohup ./eval/run_overnight.sh > eval/overnight.log 2>&1 &
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${DIGIMON_PYTHON:-${PYTHON:-python}}"
DATASET=HotpotQA_200

echo "========================================"
echo "OVERNIGHT BENCHMARK: $DATASET"
echo "Started: $(date)"
echo "========================================"

# Step 1: Pre-build graph + VDBs
echo ""
echo "[Phase 1] Building graph + VDBs (~20-40 min)..."
"$PYTHON" eval/prebuild_graph.py "$DATASET"
echo "[Phase 1] Complete: $(date)"

# Step 2: Run agent benchmark
echo ""
echo "[Phase 2] Running agent benchmark (200 questions, ~2-3 hours)..."
"$PYTHON" eval/run_agent_benchmark.py \
    --dataset $DATASET \
    --n 200 \
    --model "gemini/gemini-3-flash-preview" \
    --timeout 0 \
    --max-turns 25

echo ""
echo "========================================"
echo "OVERNIGHT BENCHMARK COMPLETE"
echo "Finished: $(date)"
echo "========================================"
