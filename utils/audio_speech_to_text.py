import json
import os
import queue
import threading
import time
import pyaudio
import websockets.sync.client as ws_sync
from io import BytesIO
from typing import Callable, Optional
from urllib.parse import urlencode
from mutagen.mp3 import MP3
from utils.reps_sets_exercise_hanlder import parse_llm_control_signals, extract_control_signals_from_text


WS_URL      = "wss://streaming.assemblyai.com/v3/ws"
SAMPLE_RATE = 16_000
CHUNK       = 1024          # ~64ms per chunk at 16kHz
SILENCE     = b"\x00" * CHUNK * 2   # PCM16 silence = 2 bytes per sample


def _mp3_duration_seconds(mp3_bytes: bytes) -> float:
    if not mp3_bytes:
        return 0.0
    try:
        audio = MP3(BytesIO(mp3_bytes))
        return audio.info.length
    except Exception:
        # Rough fallback: ~128 kbps MP3 → 16000 bytes/sec
        return len(mp3_bytes) / 16_000


class AudioCommandPipeline:
    """
    PyAudio mic → AssemblyAI v3 STT →
    handle_user_command(text) → synthesize_speech(text) → autoplay bytes.

    Mic is muted for the duration of TTS playback + a small tail buffer
    so AssemblyAI never hears the speaker output.
    """

    # Extra silence after TTS ends before we re-open the mic (seconds)
    MIC_REOPEN_TAIL = 0.6

    def __init__(
        self,
        handle_user_command: Callable[..., str],
        synthesize_speech:   Callable[[str], bytes],
        sample_rate: int     = SAMPLE_RATE,
        api_key: Optional[str] = None,
    ):
        self.handle_user_command = handle_user_command
        self.synthesize_speech   = synthesize_speech
        self.sample_rate         = sample_rate
        self.api_key             = api_key or os.getenv("ASSEMBLYAI_API_KEY", "")

        self._transcript_q: queue.Queue[str]  = queue.Queue(maxsize=64)
        self._response_q:   queue.Queue[dict] = queue.Queue(maxsize=32)

        self._stop_event = threading.Event()
        self._mute_event = threading.Event()   
        self._ws         = None

        self._ws_thread:      Optional[threading.Thread] = None
        self._command_thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self._ws_thread is not None and self._ws_thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        if not self.api_key:
            raise RuntimeError("ASSEMBLYAI_API_KEY is missing")
        self._stop_event.clear()
        self._mute_event.clear()
        self._ws_thread      = threading.Thread(target=self._ws_loop,       daemon=True)
        self._command_thread = threading.Thread(target=self._command_loop,  daemon=True)
        self._ws_thread.start()
        self._command_thread.start()
        print("[AudioCommandPipeline] started")

    def stop(self) -> None:
        print("[AudioCommandPipeline] stop() called")
        self._stop_event.set()
        self._mute_event.set()  
        ws = self._ws

        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=4.0)
        if self._command_thread and self._command_thread.is_alive():
            self._command_thread.join(timeout=1.0)

        self._ws             = None
        self._ws_thread      = None
        self._command_thread = None

        print("[AudioCommandPipeline] stopped")

    def mute_for(self, seconds: float) -> None:
        """
        Mute the mic for `seconds` then automatically unmute.
        Called just before the TTS audio is handed to the browser.
        """
        if seconds <= 0:
            return

        def _unmute():
            end = time.monotonic() + seconds + self.MIC_REOPEN_TAIL
            while time.monotonic() < end:
                if self._stop_event.is_set():
                    return
                time.sleep(0.05)
            self._mute_event.clear()
            print(f"[AudioCommandPipeline] mic unmuted after {seconds:.1f}s TTS")

        self._mute_event.set()
        print(f"[AudioCommandPipeline] mic muted for ~{seconds:.1f}s (TTS playing)")
        threading.Thread(target=_unmute, daemon=True).start()

    def pop_latest_response(self) -> Optional[dict]:
        """Return the most recent response payload, or None."""
        latest = None
        while True:
            try:
                latest = self._response_q.get_nowait()
            except queue.Empty:
                break
        return latest

    def _ws_loop(self) -> None:
        params = {
            "sample_rate":  self.sample_rate,
            "encoding":     "pcm_s16le",
            "speech_model": "universal-streaming-english",
            "format_turns": False,
            "end_of_turn_confidence_threshold":       0.4,
            "min_end_of_turn_silence_when_confident": 400,
            "max_turn_silence":                       1280,
        }
        url     = f"{WS_URL}?{urlencode(params)}"
        headers = {"Authorization": self.api_key}
        pa     = pyaudio.PyAudio()
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=CHUNK,
        )

        try:
            with ws_sync.connect(url, additional_headers=headers) as ws:
                self._ws = ws
                print("[AudioCommandPipeline] WebSocket connected")

                sender = threading.Thread(
                    target=self._mic_sender, args=(ws, stream), daemon=True
                )
                sender.start()

                for raw in ws:
                    if self._stop_event.is_set():
                        break
                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue

                    kind = data.get("type")

                    if kind == "Begin":
                        print(f"[AudioCommandPipeline] Session ID: {data.get('id')}")

                    elif kind == "Turn":
                        transcript  = (data.get("transcript") or "").strip()
                        end_of_turn = data.get("end_of_turn", False)
                        if transcript:
                            print(f"[AudioCommandPipeline] '{transcript}' eot={end_of_turn}")
                        if end_of_turn and transcript:
                            try:
                                self._transcript_q.put_nowait(transcript)
                            except queue.Full:
                                pass

                    elif kind == "Termination":
                        print("[AudioCommandPipeline] Session terminated by server")
                        break

                print("[AudioCommandPipeline] receive loop exited")

        except Exception as exc:
            if not self._stop_event.is_set():
                print(f"[AudioCommandPipeline] WS error: {exc}")
        finally:
            self._ws = None
            try:
                stream.stop_stream()
                stream.close()
                pa.terminate()
            except Exception:
                pass
            print("[AudioCommandPipeline] mic closed")

    def _mic_sender(self, ws, stream: pyaudio.Stream) -> None:
        """Send mic PCM to WebSocket — replaces with silence while muted."""
        sent = 0

        while not self._stop_event.is_set():
            try:
                if self._mute_event.is_set():
                    try:
                        stream.read(CHUNK, exception_on_overflow=False)
                    except Exception:
                        pass
                    ws.send(SILENCE) 
                else:
                    audio = stream.read(CHUNK, exception_on_overflow=False)
                    ws.send(audio)

                sent += 1
                if sent % 100 == 0:
                    muted = "🔇 MUTED" if self._mute_event.is_set() else "🎤 live"
                    print(f"[AudioCommandPipeline] {sent} chunks sent ({muted})")

            except Exception as exc:
                if not self._stop_event.is_set():
                    print(f"[AudioCommandPipeline] mic sender error: {exc}")
                break

        print(f"[AudioCommandPipeline] sender done — {sent} total chunks")

    def _command_loop(self) -> None:
        """Transcript → LLM → TTS → mute mic → enqueue response."""
        while not self._stop_event.is_set():
            try:
                text = self._transcript_q.get(timeout=0.3)
            except queue.Empty:
                continue
            if not text:
                continue
            try:
                transcript_signals = extract_control_signals_from_text(text)
                requested_exercise = transcript_signals.get("target_exercise")

                try:
                    raw_response_text = self.handle_user_command(text, requested_exercise) 
                except TypeError:
                    raw_response_text = self.handle_user_command(text)

                signals = parse_llm_control_signals(raw_response_text)
                resolved_goal_sets = signals.goal_sets

                if resolved_goal_sets is None:
                    resolved_goal_sets = transcript_signals.get("goal_sets")

                resolved_goal_reps = signals.goal_reps

                if resolved_goal_reps is None:
                    resolved_goal_reps = transcript_signals.get("goal_reps")

                resolved_exercise = signals.target_exercise

                if resolved_exercise is None:
                    resolved_exercise = transcript_signals.get("target_exercise")

                response_text = signals.response_text
                audio_bytes   = self.synthesize_speech(response_text)

                # Estimate TTS duration and mute BEFORE handing audio to browser
                tts_duration = _mp3_duration_seconds(audio_bytes)
                
                if tts_duration > 0:
                    self.mute_for(tts_duration)

                try:
                    self._response_q.put_nowait({
                        "transcript":    text,
                        "response_text": response_text,
                        "raw_response_text": raw_response_text,
                        "audio_bytes":   audio_bytes,
                        "control_signals": {
                            "goal_sets": resolved_goal_sets,
                            "goal_reps": resolved_goal_reps,
                            "target_exercise": resolved_exercise,
                        },
                    })
                except queue.Full:
                    pass

            except Exception as exc:
                print(f"[AudioCommandPipeline] command error: {exc}")
                