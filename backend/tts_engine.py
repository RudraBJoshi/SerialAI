"""TTS engine using edge-tts (high quality) with pyttsx3 fallback."""

import asyncio
import threading
import os
import sys
import tempfile
import io

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False


VOICE = "en-US-GuyNeural"  # Deep male voice — closest to J.A.R.V.I.S.
RATE = "+5%"
VOLUME = "+0%"


class TTSEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self._speaking = False
        self._pyttsx3_engine = None

        if not EDGE_TTS_AVAILABLE and PYTTSX3_AVAILABLE:
            self._init_pyttsx3()

    def _init_pyttsx3(self):
        try:
            self._pyttsx3_engine = pyttsx3.init()
            voices = self._pyttsx3_engine.getProperty("voices")
            # Prefer a male voice
            for voice in voices:
                if "male" in voice.name.lower() or "david" in voice.name.lower():
                    self._pyttsx3_engine.setProperty("voice", voice.id)
                    break
            self._pyttsx3_engine.setProperty("rate", 175)
            self._pyttsx3_engine.setProperty("volume", 0.9)
        except Exception:
            self._pyttsx3_engine = None

    def speak(self, text: str, on_done: callable = None):
        """Speak text in a background thread."""
        def _run():
            with self._lock:
                self._speaking = True
                try:
                    if EDGE_TTS_AVAILABLE:
                        self._speak_edge(text)
                    elif self._pyttsx3_engine:
                        self._speak_pyttsx3(text)
                finally:
                    self._speaking = False
                    if on_done:
                        on_done()

        t = threading.Thread(target=_run, daemon=True)
        t.start()

    def _speak_edge(self, text: str):
        async def _async_speak():
            communicate = edge_tts.Communicate(text, VOICE, rate=RATE, volume=VOLUME)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                await communicate.save(tmp_path)
                # Play using Windows Media Player or system default
                if sys.platform == "win32":
                    import subprocess
                    subprocess.run(
                        ["powershell", "-c", f"(New-Object Media.SoundPlayer).PlaySync()"],
                        capture_output=True
                    )
                    # Better: use Windows built-in player
                    os.startfile(tmp_path)
                    import time
                    time.sleep(len(text) * 0.065 + 1.0)
                else:
                    # Linux fallback for dev
                    os.system(f"mpg123 -q '{tmp_path}' 2>/dev/null || play '{tmp_path}' 2>/dev/null")
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

        asyncio.run(_async_speak())

    def _speak_pyttsx3(self, text: str):
        try:
            self._pyttsx3_engine.say(text)
            self._pyttsx3_engine.runAndWait()
        except Exception:
            pass

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    def stop(self):
        """Interrupt current speech (best-effort)."""
        if self._pyttsx3_engine:
            try:
                self._pyttsx3_engine.stop()
            except Exception:
                pass
