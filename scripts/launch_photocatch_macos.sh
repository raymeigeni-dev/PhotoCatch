#!/usr/bin/env bash
set -Eeuo pipefail

# PhotoCatch one-click local launcher for macOS.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Include user-local OpenMVS binaries installed by scripts/install_openmvs_macos_arm64.sh.
export PATH="${HOME}/.local/bin:${PATH}"

BACKEND_PORT="${PHOTOCATCH_BACKEND_PORT:-5051}"
FRONTEND_PORT="${PHOTOCATCH_FRONTEND_PORT:-8000}"
PYTHON="${ROOT}/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "PhotoCatch Python environment is missing: $PYTHON"
  echo "Create it with: python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

if ! "$PYTHON" -c 'import flask, cv2, numpy, requests, trimesh' >/dev/null 2>&1; then
  echo "PhotoCatch dependencies are incomplete."
  echo "Run: .venv/bin/pip install -r requirements.txt"
  exit 1
fi

# Build the native Apple Object Capture helper when Swift/Xcode tools are available.
# Keep the other engines launchable if the optional native build fails.
if [[ "$(uname -s)" == "Darwin" ]] && command -v swift >/dev/null 2>&1; then
  echo "Building Apple Object Capture helper (optional native engine)..."
  if (cd "$ROOT/native/apple-object-capture" && swift build -c release); then
    echo "Apple Object Capture helper build succeeded."
  else
    echo "WARNING: Apple Object Capture helper did not build. Other routes can still launch."
    echo "See the build output above; the test window will report Apple as unavailable."
  fi
else
  echo "WARNING: Swift/Xcode command-line tools not found; Apple helper was not built."
fi

port_busy() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

if port_busy "$BACKEND_PORT"; then
  echo "Backend port $BACKEND_PORT is already in use. No process was stopped."
  echo "Set PHOTOCATCH_BACKEND_PORT to another free port and relaunch."
  exit 1
fi
if port_busy "$FRONTEND_PORT"; then
  echo "Frontend port $FRONTEND_PORT is already in use. No process was stopped."
  echo "Set PHOTOCATCH_FRONTEND_PORT to another free port and relaunch."
  exit 1
fi

LOG_DIR="${HOME}/Library/Logs/PhotoCatch"
mkdir -p "$LOG_DIR"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  [[ -z "$BACKEND_PID" ]] || kill "$BACKEND_PID" 2>/dev/null || true
  [[ -z "$FRONTEND_PID" ]] || kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

PORT="$BACKEND_PORT" HOST=127.0.0.1 LOG_LEVEL=INFO "$PYTHON" -m backend.server >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
python3 -m http.server "$FRONTEND_PORT" --bind 127.0.0.1 --directory "$ROOT" >"$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

URL="http://127.0.0.1:$FRONTEND_PORT/frontend/reconstruction-lab.html?api=http://127.0.0.1:$BACKEND_PORT"
echo "Starting PhotoCatch..."
echo "UI: $URL"
echo "Backend log: $BACKEND_LOG"
echo "Frontend log: $FRONTEND_LOG"

for _ in $(seq 1 40); do
  if curl -fsS --max-time 2 "http://127.0.0.1:$BACKEND_PORT/api/health" >/dev/null; then
    break
  fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "Backend exited during startup. Last log lines:"
    tail -80 "$BACKEND_LOG"
    exit 1
  fi
  sleep 0.5
done

if ! curl -fsS --max-time 2 "http://127.0.0.1:$BACKEND_PORT/api/health"; then
  echo
  echo "Backend health check failed. See $BACKEND_LOG"
  exit 1
fi
echo
open "$URL" 2>/dev/null || echo "Open this URL in your browser: $URL"
echo "PhotoCatch is running. Keep this terminal open; press Ctrl+C to stop both local servers."
wait
