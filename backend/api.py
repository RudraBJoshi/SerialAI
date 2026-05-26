"""Flask API + SocketIO server for Serial AI."""

import os
import sys
import threading
import json
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit

from backend.ai_engine import AIEngine
from backend.tts_engine import TTSEngine
from backend.stt_engine import STTEngine
from backend import system_manager as sm

app = Flask(__name__, static_folder=None)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Globals — initialized by main.py after API key is loaded
gemini: AIEngine = None
tts: TTSEngine = None
stt: STTEngine = None


_TOOL_LABELS = {
    "web_search":          "SEARCHING WEB",
    "get_system_info":     "SCANNING SYSTEM",
    "list_processes":      "READING PROCESSES",
    "kill_process":        "TERMINATING PROCESS",
    "search_files":        "SEARCHING FILES",
    "launch_application":  "LAUNCHING APP",
    "get_network_stats":   "READING NETWORK",
    "get_startup_programs":"READING STARTUP",
    "set_volume":          "ADJUSTING VOLUME",
    "shutdown_serial_ai":  "SHUTTING DOWN",
    "run_powershell":      "RUNNING POWERSHELL",
    "thinking":            "THINKING",
}

def init_engines(api_key: str):
    global gemini, tts, stt

    def on_tool_status(name: str):
        label = _TOOL_LABELS.get(name, name.replace("_", " ").upper())
        socketio.emit("ai_tool_status", {"label": label})

    gemini = AIEngine(api_key, on_status=on_tool_status)
    tts = TTSEngine()
    stt = STTEngine()

    def on_stt_status(status: str):
        socketio.emit("stt_status", {"status": status})

    def on_stt_result(text: str):
        socketio.emit("stt_result", {"text": text})
        _handle_message(text)

    stt.set_callbacks(on_stt_status, on_stt_result)


def _handle_message(user_text: str):
    """Core: send to Gemini, TTS the reply, emit to frontend."""
    socketio.emit("user_message", {"text": user_text})
    socketio.emit("ai_status", {"status": "thinking"})
    socketio.emit("ai_tool_status", {"label": "THINKING"})

    context = sm.get_system_snapshot()
    reply = gemini.send_message(user_text, system_context=context)

    socketio.emit("ai_message", {"text": reply})
    socketio.emit("ai_status", {"status": "speaking"})

    def on_speech_done():
        socketio.emit("ai_status", {"status": "idle"})

    if tts:
        tts.speak(reply, on_done=on_speech_done)
    else:
        socketio.emit("ai_status", {"status": "idle"})


# ── REST Endpoints ─────────────────────────────────────────────────────────────

BUILD_TIME = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@app.route("/api/health")
def health():
    return jsonify({"status": "online", "gemini": gemini is not None, "started": BUILD_TIME})


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json()
    text = (data or {}).get("message", "").strip()
    if not text:
        return jsonify({"error": "Empty message"}), 400

    threading.Thread(target=_handle_message, args=(text,), daemon=True).start()
    return jsonify({"status": "processing"})


@app.route("/api/system/snapshot")
def system_snapshot():
    return jsonify(sm.get_system_snapshot())


@app.route("/api/system/info")
def system_info():
    return jsonify(sm.get_full_system_info())


@app.route("/api/system/processes")
def processes():
    sort_by = request.args.get("sort", "cpu")
    limit = int(request.args.get("limit", 20))
    return jsonify(sm.list_processes(sort_by=sort_by, limit=limit))


@app.route("/api/system/kill", methods=["POST"])
def kill_process():
    data = request.get_json()
    identifier = (data or {}).get("identifier")
    if identifier is None:
        return jsonify({"error": "No identifier"}), 400
    return jsonify(sm.kill_process(identifier))


@app.route("/api/system/network")
def network():
    return jsonify(sm.get_network_stats())


@app.route("/api/system/startup")
def startup():
    return jsonify(sm.get_startup_programs())


@app.route("/api/search/files", methods=["POST"])
def search_files():
    data = request.get_json()
    query = (data or {}).get("query", "")
    path = (data or {}).get("path")
    if not query:
        return jsonify({"error": "No query"}), 400
    results = sm.search_files(query, search_path=path)
    return jsonify({"results": results, "count": len(results)})


@app.route("/api/app/launch", methods=["POST"])
def launch_app():
    data = request.get_json()
    app_name = (data or {}).get("name", "")
    return jsonify(sm.launch_application(app_name))


@app.route("/api/volume", methods=["POST"])
def set_volume():
    data = request.get_json()
    level = (data or {}).get("level", 50)
    return jsonify(sm.set_volume(int(level)))


@app.route("/api/voice/start", methods=["POST"])
def voice_start():
    if not stt:
        return jsonify({"error": "STT not initialized"}), 503
    success = stt.start_listening()
    return jsonify({"listening": success})


@app.route("/api/voice/stop", methods=["POST"])
def voice_stop():
    if stt:
        stt.stop_listening()
    return jsonify({"listening": False})


@app.route("/api/conversation/reset", methods=["POST"])
def reset():
    if gemini:
        gemini.reset_conversation()
    return jsonify({"status": "reset"})


@app.route("/api/conversation/history")
def history():
    if not gemini:
        return jsonify([])
    return jsonify(gemini.get_history())


@app.route("/api/shutdown", methods=["POST"])
def shutdown():
    """Tell the frontend to close, then exit the process."""
    def _do_exit():
        import time, os
        socketio.emit("shutdown", {"message": "Serial AI shutting down."})
        time.sleep(0.8)
        os._exit(0)
    threading.Thread(target=_do_exit, daemon=True).start()
    return jsonify({"status": "shutting_down"})


# ── SocketIO Events ────────────────────────────────────────────────────────────

@socketio.on("connect")
def on_connect():
    emit("connected", {"message": "SERIAL AI online."})


@socketio.on("chat_message")
def on_chat_message(data):
    text = (data or {}).get("text", "").strip()
    if text:
        threading.Thread(target=_handle_message, args=(text,), daemon=True).start()


def run_server(host: str = "127.0.0.1", port: int = 5000):
    socketio.run(app, host=host, port=port, debug=False, use_reloader=False, log_output=False, allow_unsafe_werkzeug=True)
