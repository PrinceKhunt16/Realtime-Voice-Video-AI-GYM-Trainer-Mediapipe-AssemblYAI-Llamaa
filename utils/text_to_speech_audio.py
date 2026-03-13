from io import BytesIO
from gtts import gTTS


def synthesize_speech(text: str, lang: str = "en") -> bytes:
    """Convert response text to MP3 bytes for playback in Streamlit."""
    cleaned = (text or "").strip()
    
    if not cleaned:
        return b""

    try:
        buf = BytesIO()
        gTTS(text=cleaned, lang=lang).write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception:
        return b""

# import os
# from elevenlabs import ElevenLabs
# from dotenv import load_dotenv

# load_dotenv()


# _API_KEY  = os.getenv("ELEVENLABS_API_KEY", "")
# _VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")
# _MODEL_ID = "eleven_multilingual_v2"
# _FORMAT   = "mp3_44100_128"

# _client: ElevenLabs | None = None


# def _get_client() -> ElevenLabs:
#     """Lazy-init singleton client."""
#     global _client
#     if _client is None:
#         if not _API_KEY:
#             raise RuntimeError("ELEVENLABS_API_KEY is not set in environment")
#         _client = ElevenLabs(api_key=_API_KEY)
#     return _client


# def synthesize_speech(text: str) -> bytes:
#     """
#     Convert text → MP3 bytes using ElevenLabs.
#     Returns empty bytes on failure so the pipeline stays alive.
#     """
#     cleaned = (text or "").strip()
#     if not cleaned:
#         return b""

#     try:
#         client = _get_client()

#         # Returns a generator of audio chunks
#         audio_stream = client.text_to_speech.convert(
#             voice_id=_VOICE_ID,
#             text=cleaned,
#             model_id=_MODEL_ID,
#             output_format=_FORMAT,
#         )

#         # Collect all chunks into a single bytes object
#         return b"".join(audio_stream)

#     except Exception as exc:
#         print(f"[tts_handler] ElevenLabs error: {exc}")
#         return b""
