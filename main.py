"""
SERIAL AI — Entry Point
Auto-detects environment:
  - Windows native → PyWebView frameless window
  - WSL2           → Edge/Chrome in --app mode via powershell.exe
  - --browser flag → system default browser
"""

import os
import sys
import subprocess
import threading
import time
import argparse
import socket
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

API_KEY      = os.getenv("OPENROUTER_API_KEY", "").strip()
HOST         = "127.0.0.1"
PORT         = 5000
FRONTEND_DIR = Path(__file__).parent / "frontend"
URL          = f"http://localhost:{PORT}/ui/"   # localhost works from both WSL and Windows

WIDTH, HEIGHT = 1400, 860

EDGE_PATH   = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


# ── Environment detection ──────────────────────────────────────────────────────

def is_wsl() -> bool:
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


# ── API key check ──────────────────────────────────────────────────────────────

def check_api_key():
    if not API_KEY:
        print("\n[ERROR] OPENROUTER_API_KEY not set. Add it to your .env file.\n")
        sys.exit(1)


# ── Frontend routes ────────────────────────────────────────────────────────────

def register_frontend_routes():
    from backend.api import app
    from flask import send_from_directory, redirect

    @app.route("/ui")
    def ui_redirect():
        return redirect("/ui/")

    @app.route("/ui/")
    def ui_index():
        return send_from_directory(str(FRONTEND_DIR), "index.html")

    @app.route("/ui/<path:path>")
    def ui_static(path):
        return send_from_directory(str(FRONTEND_DIR), path)


# ── Backend startup ────────────────────────────────────────────────────────────

def start_backend():
    from backend.api import init_engines, run_server

    print("[SERIAL AI] Initializing engines...")
    init_engines(API_KEY)

    t = threading.Thread(
        target=run_server,
        kwargs={"host": "0.0.0.0", "port": PORT},
        daemon=True,
    )
    t.start()

    for _ in range(40):
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
                print(f"[SERIAL AI] Server ready → {URL}")
                return
        except OSError:
            time.sleep(0.25)
    print("[SERIAL AI] Warning: server took longer than expected to start.")


# ── WSL2: open Edge/Chrome in --app mode via PowerShell ───────────────────────

def launch_wsl_window():
    app_args = (
        f"--app={URL} --window-size={WIDTH},{HEIGHT} "
        "--window-position=80,40 --no-first-run --disable-extensions"
    )
    ps_script = f"""
$browsers = @('{EDGE_PATH}', '{CHROME_PATH}')
foreach ($b in $browsers) {{
    if (Test-Path $b) {{
        Start-Process $b '{app_args}'
        exit 0
    }}
}}
Write-Error 'No compatible browser found'
exit 1
"""
    try:
        result = subprocess.run(
            ["powershell.exe", "-WindowStyle", "Hidden", "-command", ps_script],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            print("[SERIAL AI] App window opened via Edge/Chrome.")
            return True
        else:
            print(f"[SERIAL AI] PowerShell error: {result.stderr.strip()}")
            return False
    except FileNotFoundError:
        print("[SERIAL AI] powershell.exe not found — are you in WSL2?")
        return False
    except subprocess.TimeoutExpired:
        return False


# ── Windows native: PyWebView frameless window ────────────────────────────────

class _WindowAPI:
    def __init__(self): self._w = None
    def set_window(self, w): self._w = w
    def minimize(self):
        if self._w: self._w.minimize()
    def close_window(self):
        if self._w: self._w.destroy()


def launch_native_window():
    try:
        import webview
        api = _WindowAPI()
        w = webview.create_window(
            title="SERIAL AI",
            url=URL,
            js_api=api,
            width=WIDTH,
            height=HEIGHT,
            min_size=(960, 620),
            background_color="#020b14",
            frameless=True,
            easy_drag=True,
            text_select=False,
        )
        api.set_window(w)
        webview.start(debug=False, private_mode=False)
    except ImportError:
        print("[SERIAL AI] pywebview not available — opening browser.")
        import webbrowser
        webbrowser.open(URL)
        _wait()
    except Exception as e:
        print(f"[SERIAL AI] Window error: {e}")
        _wait()


def _wait():
    print(f"[SERIAL AI] Running at {URL}  (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SERIAL AI] Shutting down.")


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SERIAL AI")
    parser.add_argument("--browser", action="store_true",
                        help="Open in system browser instead of app window")
    args = parser.parse_args()

    print("""
╔═══════════════════════════════════════╗
║          S E R I A L  A I             ║
║    Voice-Activated System Assistant   ║
╚═══════════════════════════════════════╝""")

    check_api_key()
    register_frontend_routes()
    start_backend()

    if args.browser:
        import webbrowser
        webbrowser.open(URL)
        print(f"[SERIAL AI] Opened browser → {URL}")
        _wait()
    elif is_wsl():
        print("[SERIAL AI] WSL2 detected — launching app window via PowerShell...")
        if not launch_wsl_window():
            print(f"[SERIAL AI] Open manually: {URL}")
        _wait()
    else:
        # Windows native (or Linux with WSLg)
        launch_native_window()


if __name__ == "__main__":
    main()
