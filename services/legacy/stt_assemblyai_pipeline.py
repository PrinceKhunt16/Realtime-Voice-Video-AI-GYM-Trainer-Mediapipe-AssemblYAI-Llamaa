"""
[STT-DISABLED] Speech-to-Text pipeline using AssemblyAI.

This entire module has been disabled as part of the architecture redesign.
The new approach uses proactive, camera-driven AI coaching (no microphone needed).

To re-enable, uncomment the code below and rewire it in services/coaching/feedback_pipeline.py:
  - Import AudioCommandPipeline
  - Call pipeline.start() / pipeline.stop() around the webrtc session
  - Read pipeline.pop_latest_response() each rerun cycle

Original authors: see git history.
"""

# ---------------------------------------------------------------------------
# [STT-DISABLED - AssemblyAI streaming pipeline]
# ---------------------------------------------------------------------------

# import json
# import os
# import queue
# import threading
# import time
# import pyaudio
# import websockets.sync.client as ws_sync
# from io import BytesIO
# from typing import Callable, Optional
# from urllib.parse import urlencode
# from mutagen.mp3 import MP3
#
#
# WS_URL      = "wss://streaming.assemblyai.com/v3/ws"
# SAMPLE_RATE = 16_000
# CHUNK       = 1024          # ~64ms per chunk at 16kHz
# SILENCE     = b"\x00" * CHUNK * 2   # PCM16 silence = 2 bytes per sample
#
#
# def _mp3_duration_seconds(mp3_bytes: bytes) -> float:
#     if not mp3_bytes:
#         return 0.0
#     try:
#         audio = MP3(BytesIO(mp3_bytes))
#         return audio.info.length
#     except Exception:
#         return len(mp3_bytes) / 16_000
#
#
# class AudioCommandPipeline:
#     """
#     PyAudio mic → AssemblyAI v3 STT →
#     handle_user_command(text) → synthesize_speech(text) → autoplay bytes.
#
#     Mic is muted for the duration of TTS playback + a small tail buffer
#     so AssemblyAI never hears the speaker output.
#     """
#
#     MIC_REOPEN_TAIL = 0.6
#
#     def __init__(
#         self,
#         handle_user_command: Callable[..., str],
#         synthesize_speech:   Callable[[str], bytes],
#         sample_rate: int     = SAMPLE_RATE,
#         api_key: Optional[str] = None,
#     ):
#         self.handle_user_command = handle_user_command
#         self.synthesize_speech   = synthesize_speech
#         self.sample_rate         = sample_rate
#         self.api_key             = api_key or os.getenv("ASSEMBLYAI_API_KEY", "")
#
#         self._transcript_q: queue.Queue[str]  = queue.Queue(maxsize=64)
#         self._response_q:   queue.Queue[dict] = queue.Queue(maxsize=32)
#         self._stop_event = threading.Event()
#         self._mute_event = threading.Event()
#         self._ws         = None
#         self._ws_thread:      Optional[threading.Thread] = None
#         self._command_thread: Optional[threading.Thread] = None
#
#     @property
#     def running(self) -> bool:
#         return self._ws_thread is not None and self._ws_thread.is_alive()
#
#     def start(self) -> None:
#         if self.running:
#             return
#         if not self.api_key:
#             raise RuntimeError("ASSEMBLYAI_API_KEY is missing")
#         self._stop_event.clear()
#         self._mute_event.clear()
#         self._ws_thread      = threading.Thread(target=self._ws_loop,      daemon=True)
#         self._command_thread = threading.Thread(target=self._command_loop, daemon=True)
#         self._ws_thread.start()
#         self._command_thread.start()
#
#     def stop(self) -> None:
#         self._stop_event.set()
#         self._mute_event.set()
#         ws = self._ws
#         if ws is not None:
#             try:
#                 ws.close()
#             except Exception:
#                 pass
#         if self._ws_thread and self._ws_thread.is_alive():
#             self._ws_thread.join(timeout=4.0)
#         if self._command_thread and self._command_thread.is_alive():
#             self._command_thread.join(timeout=1.0)
#         self._ws = self._ws_thread = self._command_thread = None
#
#     def mute_for(self, seconds: float) -> None:
#         if seconds <= 0:
#             return
#         def _unmute():
#             end = time.monotonic() + seconds + self.MIC_REOPEN_TAIL
#             while time.monotonic() < end:
#                 if self._stop_event.is_set():
#                     return
#                 time.sleep(0.05)
#             self._mute_event.clear()
#         self._mute_event.set()
#         threading.Thread(target=_unmute, daemon=True).start()
#
#     def pop_latest_response(self) -> Optional[dict]:
#         latest = None
#         while True:
#             try:
#                 latest = self._response_q.get_nowait()
#             except queue.Empty:
#                 break
#         return latest
#
#     def _ws_loop(self) -> None:
#         params = {
#             "sample_rate":  self.sample_rate,
#             "encoding":     "pcm_s16le",
#             "speech_model": "universal-streaming-english",
#             "format_turns": False,
#             "end_of_turn_confidence_threshold":       0.4,
#             "min_end_of_turn_silence_when_confident": 400,
#             "max_turn_silence":                       1280,
#         }
#         url     = f"{WS_URL}?{urlencode(params)}"
#         headers = {"Authorization": self.api_key}
#         pa     = pyaudio.PyAudio()
#         stream = pa.open(
#             format=pyaudio.paInt16, channels=1,
#             rate=self.sample_rate, input=True, frames_per_buffer=CHUNK,
#         )
#         try:
#             with ws_sync.connect(url, additional_headers=headers) as ws:
#                 self._ws = ws
#                 sender = threading.Thread(
#                     target=self._mic_sender, args=(ws, stream), daemon=True
#                 )
#                 sender.start()
#                 for raw in ws:
#                     if self._stop_event.is_set():
#                         break
#                     try:
#                         data = json.loads(raw)
#                     except Exception:
#                         continue
#                     kind = data.get("type")
#                     if kind == "Turn":
#                         transcript  = (data.get("transcript") or "").strip()
#                         end_of_turn = data.get("end_of_turn", False)
#                         if end_of_turn and transcript:
#                             try:
#                                 self._transcript_q.put_nowait(transcript)
#                             except queue.Full:
#                                 pass
#                     elif kind == "Termination":
#                         break
#         except Exception as exc:
#             if not self._stop_event.is_set():
#                 print(f"[AudioCommandPipeline] WS error: {exc}")
#         finally:
#             self._ws = None
#             try:
#                 stream.stop_stream(); stream.close(); pa.terminate()
#             except Exception:
#                 pass
#
#     def _mic_sender(self, ws, stream: "pyaudio.Stream") -> None:
#         while not self._stop_event.is_set():
#             try:
#                 if self._mute_event.is_set():
#                     try:
#                         stream.read(CHUNK, exception_on_overflow=False)
#                     except Exception:
#                         pass
#                     ws.send(SILENCE)
#                 else:
#                     audio = stream.read(CHUNK, exception_on_overflow=False)
#                     ws.send(audio)
#             except Exception:
#                 break
#
#     def _command_loop(self) -> None:
#         while not self._stop_event.is_set():
#             try:
#                 text = self._transcript_q.get(timeout=0.3)
#             except queue.Empty:
#                 continue
#             if not text:
#                 continue
#             try:
#                 raw_response_text = self.handle_user_command(text)
#                 response_text = raw_response_text
#                 audio_bytes   = self.synthesize_speech(response_text)
#                 tts_duration  = _mp3_duration_seconds(audio_bytes)
#                 if tts_duration > 0:
#                     self.mute_for(tts_duration)
#                 try:
#                     self._response_q.put_nowait({
#                         "transcript":    text,
#                         "response_text": response_text,
#                         "audio_bytes":   audio_bytes,
#                     })
#                 except queue.Full:
#                     pass
#             except Exception as exc:
#                 print(f"[AudioCommandPipeline] command error: {exc}")