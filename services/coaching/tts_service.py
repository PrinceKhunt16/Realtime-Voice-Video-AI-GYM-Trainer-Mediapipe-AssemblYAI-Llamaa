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
    