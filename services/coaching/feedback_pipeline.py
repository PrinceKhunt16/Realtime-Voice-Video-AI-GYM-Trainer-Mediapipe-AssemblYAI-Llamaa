"""
Voice output service: TTS (text-to-speech) + browser audio injection.

The STT (speech-to-text / AssemblyAI microphone pipeline) that previously
lived in services/legacy/stt_assemblyai_pipeline.py has been DISABLED as part of the
architecture redesign. The new flow is camera-only: the AI coach watches
pose metrics and speaks proactively — the user does NOT need to speak.

To re-enable STT in the future, see the commented-out code in:
    services/legacy/stt_assemblyai_pipeline.py  (AudioCommandPipeline class)
"""

import base64
import streamlit as st
import streamlit.components.v1 as components
from services.coaching.coach_llm import GroqCoach
from services.coaching.feedback_engine import FeedbackEngine
from services.coaching.tts_service import synthesize_speech


def initialize_voice_state() -> None:
    """Set up session-state keys for the proactive voice coach."""
    defaults = {
        "latest_coach_text": "",
        "latest_audio_bytes": b"",
        "groq_coach": GroqCoach(),
        "feedback_engine": None,          # created on workout start
        "_prev_workout_started": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def ensure_feedback_engine() -> FeedbackEngine:
    """Return the FeedbackEngine for the current session, creating if needed."""
    engine: FeedbackEngine | None = st.session_state.get("feedback_engine")
    if engine is None:
        engine = FeedbackEngine(
            coach=st.session_state.groq_coach,
            synthesize_speech=synthesize_speech,
        )
        st.session_state.feedback_engine = engine
    return engine


def reset_feedback_engine() -> None:
    """Reset the engine when a new session starts (clears milestones/cooldown)."""
    engine: FeedbackEngine | None = st.session_state.get("feedback_engine")
    if engine is not None:
        engine.reset()
    else:
        st.session_state.feedback_engine = FeedbackEngine(
            coach=st.session_state.groq_coach,
            synthesize_speech=synthesize_speech,
        )


def run_feedback_tick(
    metrics: dict,
    exercise: str,
    reps: int,
    sets_completed: int,
    target_sets: int,
    reps_per_set: int,
) -> None:
    """
    Call this on every Streamlit rerun while the workout is active.

    Internally it delegates to FeedbackEngine.maybe_generate() which applies
    cooldown logic and decides whether to fire a spoken cue.
    If a cue fires, it is stored in session_state for playback.
    """
    engine = ensure_feedback_engine()
    result = engine.maybe_generate(
        metrics=metrics,
        reps=reps,
        sets_completed=sets_completed,
        target_sets=target_sets,
        reps_per_set=reps_per_set,
        exercise=exercise,
    )
    if result:
        text, audio_bytes = result
        st.session_state.latest_coach_text = text
        st.session_state.latest_audio_bytes = audio_bytes


def autoplay_audio(audio_bytes: bytes) -> None:
    """Inject a hidden <audio autoplay> tag so the browser plays immediately."""
    if not audio_bytes:
        return
    b64 = base64.b64encode(audio_bytes).decode()
    components.html(
        f"""
        <audio autoplay style="display:none">
            <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
        </audio>
        """,
        height=0,
    )


# ---------------------------------------------------------------------------
# [STT-DISABLED] — The following functions from the old architecture are
# intentionally removed. They connected the microphone → AssemblyAI pipeline:
#
#   start_voice_pipeline()
#   stop_voice_pipeline()
#   handle_user_command(text)
#   update_command_context(...)
#   generate_event_feedback_payload(...)
#
# To re-enable STT, restore AudioCommandPipeline from
# services/legacy/stt_assemblyai_pipeline.py and rewire these functions.
# ---------------------------------------------------------------------------