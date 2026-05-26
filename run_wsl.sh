#!/usr/bin/env bash
# ── SERIAL AI — WSL2 Launcher ──────────────────────────────────────────────────
# Starts the backend server then opens Edge/Chrome in --app mode.
# --app strips all browser chrome → looks like a native desktop window.

set -e
cd "$(dirname "$0")"

PORT=5000
URL="http://localhost:${PORT}/ui/"
WIDTH=1400
HEIGHT=860

# Activate venv
if [[ -f venv/bin/activate ]]; then
  source venv/bin/activate
else
  echo "[ERROR] venv not found. Run setup first."
  exit 1
fi

# ── Start backend server ───────────────────────────────────────────────────────
echo ""
echo "  ╔═══════════════════════════════════════╗"
echo "  ║          S E R I A L  A I             ║"
echo "  ║         WSL2 Test Launcher            ║"
echo "  ╚═══════════════════════════════════════╝"
echo ""
echo "[1/3] Starting backend server..."

# Kill any leftover server on this port before starting fresh
fuser -k ${PORT}/tcp 2>/dev/null || true
sleep 0.3

python - <<'PYEOF' &
import os, sys
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv('.env')
from backend.api import app, init_engines, run_server
from main import register_frontend_routes
register_frontend_routes()
key = os.getenv('OPENROUTER_API_KEY', '')
if not key:
    print('[ERROR] OPENROUTER_API_KEY not set in .env')
    sys.exit(1)
init_engines(key)
run_server('0.0.0.0', int(os.getenv('PORT', 5000)))
PYEOF

SERVER_PID=$!

# ── Wait for server ready ──────────────────────────────────────────────────────
echo "[2/3] Waiting for server..."
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${PORT}/api/health" > /dev/null 2>&1; then
    echo "      Server ready at ${URL}"
    break
  fi
  sleep 0.5
done

if ! curl -sf "http://127.0.0.1:${PORT}/api/health" > /dev/null 2>&1; then
  echo "[ERROR] Server failed to start. Check your .env and requirements."
  kill $SERVER_PID 2>/dev/null
  exit 1
fi

# ── Open app window via PowerShell ─────────────────────────────────────────────
echo "[3/3] Opening app window..."

EDGE_PATH='C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
CHROME_PATH='C:\Program Files\Google\Chrome\Application\chrome.exe'

ARGS="--app=${URL} --window-size=${WIDTH},${HEIGHT} --window-position=80,40 --no-first-run --disable-extensions"

launch_browser() {
  powershell.exe -WindowStyle Hidden -command "
    \$browsers = @('${EDGE_PATH}', '${CHROME_PATH}')
    foreach (\$b in \$browsers) {
      if (Test-Path \$b) {
        Start-Process \$b '${ARGS}'
        break
      }
    }
  " 2>/dev/null
}

launch_browser && echo "      Window opened." || echo "[WARN] Could not open app window — open ${URL} manually."

# ── Keep server alive ──────────────────────────────────────────────────────────
echo ""
echo "  Serial AI is running. Press Ctrl+C to stop."
echo "  URL: ${URL}"
echo ""

trap "echo ''; echo 'Shutting down...'; kill $SERVER_PID 2>/dev/null; exit 0" INT TERM

wait $SERVER_PID
