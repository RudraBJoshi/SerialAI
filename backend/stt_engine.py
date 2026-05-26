"""Speech-to-text engine using SpeechRecognition with Google STT."""

import threading
import queue
import time

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    SR_AVAILABLE = False


class STTEngine:
    def __init__(self):
        self._recognizer = sr.Recognizer() if SR_AVAILABLE else None
        self._microphone = None
        self._listening = False
        self._thread = None
        self._result_queue = queue.Queue()
        self._status_callback = None
        self._result_callback = None

        if SR_AVAILABLE:
            self._recognizer.energy_threshold = 300
            self._recognizer.dynamic_energy_threshold = True
            self._recognizer.pause_threshold = 0.8

    def set_callbacks(self, on_status: callable, on_result: callable):
        self._status_callback = on_status
        self._result_callback = on_result

    def _emit_status(self, status: str):
        if self._status_callback:
            self._status_callback(status)

    def start_listening(self):
        if not SR_AVAILABLE:
            self._emit_status("error")
            return False

        if self._listening:
            return False

        self._listening = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        return True

    def stop_listening(self):
        self._listening = False

    def _listen_loop(self):
        self._emit_status("calibrating")
        try:
            mic = sr.Microphone()
            with mic as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
                self._emit_status("listening")

                while self._listening:
                    try:
                        audio = self._recognizer.listen(source, timeout=5, phrase_time_limit=15)
                        self._emit_status("processing")

                        try:
                            text = self._recognizer.recognize_google(audio)
                            if text.strip() and self._result_callback:
                                self._result_callback(text.strip())
                            self._emit_status("listening")
                        except sr.UnknownValueError:
                            self._emit_status("listening")
                        except sr.RequestError as e:
                            self._emit_status("error")
                            time.sleep(1)
                            self._emit_status("listening")

                    except sr.WaitTimeoutError:
                        if self._listening:
                            self._emit_status("listening")
                    except Exception:
                        break

        except Exception as e:
            self._emit_status("error")
        finally:
            self._listening = False
            self._emit_status("idle")

    def listen_once(self) -> str:
        """Synchronously capture one phrase and return the text."""
        if not SR_AVAILABLE:
            return ""
        try:
            mic = sr.Microphone()
            with mic as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.3)
                audio = self._recognizer.listen(source, timeout=8, phrase_time_limit=15)
            return self._recognizer.recognize_google(audio)
        except Exception:
            return ""

    @property
    def is_listening(self) -> bool:
        return self._listening

    @property
    def available(self) -> bool:
        return SR_AVAILABLE
