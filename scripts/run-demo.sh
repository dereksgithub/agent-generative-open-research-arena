#!/usr/bin/env bash
# run-demo.sh - Assemble personas, run simulation, launch spatial viewer
#
# Usage:
#   ./scripts/run-demo.sh                     # MiniMax LLM (default)
#   ./scripts/run-demo.sh --provider openai    # different provider
#   ./scripts/run-demo.sh --no-llm             # heuristic only, no API key needed

set -euo pipefail
cd "$(dirname "$0")/.."

PROVIDER="minimax"
USE_LLM="--llm"
EXTRA_ARGS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --provider) PROVIDER="$2"; shift 2 ;;
    --no-llm)  USE_LLM=""; shift ;;
    *)         EXTRA_ARGS="$EXTRA_ARGS $1"; shift ;;
  esac
done

# Activate venv if present
if [[ -f .venv/bin/activate ]]; then
  source .venv/bin/activate
  echo "[*] Activated venv"
fi

# Load .env if present
if [[ -f .env ]]; then
  set -a; source .env; set +a
  echo "[*] Loaded .env"
fi

# Validate API key when using LLM
if [[ -n "$USE_LLM" ]]; then
  case "$PROVIDER" in
    minimax)   KEY_VAR="MINIMAX_API_KEY" ;;
    openai)    KEY_VAR="OPENAI_API_KEY" ;;
    anthropic) KEY_VAR="ANTHROPIC_API_KEY" ;;
    deepseek)  KEY_VAR="DEEPSEEK_API_KEY" ;;
    *)         KEY_VAR="" ;;
  esac
  if [[ -n "$KEY_VAR" && -z "${!KEY_VAR:-}" ]]; then
    echo ""
    echo "ERROR: $KEY_VAR is not set."
    echo "  1. Copy .env.example to .env"
    echo "  2. Add your $KEY_VAR"
    echo "  3. Re-run this script"
    echo ""
    exit 1
  fi
fi

echo ""
echo "=== AGORA Spatial Demo ==="
echo ""

# --- Step 1: Assemble personas into scenario ---
SCENARIO_OUT="scenarios/generated/demo_commute.yaml"
echo "[1/3] Assembling personas..."
python3 scripts/assemble_personas.py personas/demo/ \
  --template scenarios/templates/commute_base.yaml \
  --output "$SCENARIO_OUT"

# --- Step 2: Run simulation ---
echo ""
echo "[2/3] Running simulation..."
if [[ -n "$USE_LLM" ]]; then
  echo "  Provider: $PROVIDER"
  agora run "$SCENARIO_OUT" --seed 42 $USE_LLM --llm-provider "$PROVIDER" $EXTRA_ARGS
else
  echo "  Mode: heuristic (no LLM)"
  agora run "$SCENARIO_OUT" --seed 42 $EXTRA_ARGS
fi

# --- Step 3: Find the latest run and launch viewers ---
LATEST_RUN=$(ls -td runs/demo_commute/*/ 2>/dev/null | head -1)
if [[ -z "$LATEST_RUN" ]]; then
  echo "ERROR: No run output found in runs/demo_commute/"
  exit 1
fi

RUN_PATH="${LATEST_RUN#runs/}"
RUN_PATH="${RUN_PATH%/}"

echo ""
echo "[3/3] Launching viewers..."
echo "  Run path: $RUN_PATH"

# Cleanup on exit
cleanup() {
  [[ -n "${VIZ_PID:-}" ]] && kill "$VIZ_PID" 2>/dev/null || true
  [[ -n "${SPATIAL_PID:-}" ]] && kill "$SPATIAL_PID" 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM EXIT

# Start the AGORA viz server (serves the API on port 8080)
agora viz --no-browser &
VIZ_PID=$!
echo "  Viz server PID: $VIZ_PID (port 8080)"

# Wait for viz server to be ready
for i in $(seq 1 10); do
  if curl -s http://localhost:8080/api/runs > /dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

# Install spatial viewer deps if needed, then start dev server
cd viz/spatial
if [[ ! -d node_modules ]]; then
  echo "  Installing spatial viewer deps..."
  npm install --silent
fi

npx vite --open "/#${RUN_PATH}" &
SPATIAL_PID=$!

echo ""
echo "========================================="
echo "  Viz server:     http://localhost:8080"
echo "  Spatial viewer:  http://localhost:5174/#${RUN_PATH}"
echo ""
echo "  Press Ctrl+C to stop."
echo "========================================="
echo ""

wait
