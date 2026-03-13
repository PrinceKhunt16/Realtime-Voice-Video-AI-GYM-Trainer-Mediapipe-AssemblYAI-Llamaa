import base64
import streamlit as st 
import streamlit.components.v1 as components
from utils.llm_handler import GroqCoach
from utils.audio_speech_to_text import AudioCommandPipeline
from utils.var import COMMAND_CONTEXT, COMMAND_CONTEXT_LOCK
from utils.text_to_speech_audio import synthesize_speech


def update_command_context(
    coach: GroqCoach | None,
    exercise: str,
    reps: int,
    target_sets: int,
    reps_per_set: int,
) -> None:
    with COMMAND_CONTEXT_LOCK:
        COMMAND_CONTEXT["coach"]    = coach
        COMMAND_CONTEXT["exercise"] = exercise
        COMMAND_CONTEXT["reps"]     = reps
        COMMAND_CONTEXT["target_sets"] = target_sets
        COMMAND_CONTEXT["reps_per_set"] = reps_per_set


def handle_user_command(text: str, override_exercise: str | None = None) -> str:
    with COMMAND_CONTEXT_LOCK:
        coach    = COMMAND_CONTEXT["coach"]
        exercise = COMMAND_CONTEXT["exercise"]
        reps     = int(COMMAND_CONTEXT["reps"])
        target_sets = int(COMMAND_CONTEXT.get("target_sets", 0))
        reps_per_set = int(COMMAND_CONTEXT.get("reps_per_set", 0))

    active_exercise = override_exercise or exercise

    if coach is None:
        return "Keep your form controlled and your breathing steady."

    return coach.generate_response(
        text,
        exercise_type=active_exercise,
        reps=reps,
        target_sets=target_sets,
        reps_per_set=reps_per_set,
    )


def initialize_audio_state() -> None:
    defaults = {
        "voice_enabled":         False,
        "audio_pipeline":        None,
        "latest_transcript":     "",
        "latest_voice_response": "",
        "latest_audio_bytes":    b"",
        "groq_coach":            GroqCoach(),
        "_prev_stream_active":   False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def start_voice_pipeline() -> None:
    """Create and start the PyAudio → AssemblyAI pipeline."""
    pipeline = AudioCommandPipeline(
        handle_user_command=handle_user_command,
        synthesize_speech=synthesize_speech,
    )
    pipeline.start()
    st.session_state.audio_pipeline = pipeline
    print("[main] voice pipeline started")


def stop_voice_pipeline() -> None:
    """Stop the pipeline cleanly."""
    pipeline: AudioCommandPipeline | None = st.session_state.get("audio_pipeline")
    if pipeline is not None:
        pipeline.stop()
    st.session_state.audio_pipeline = None
    print("[main] voice pipeline stopped")


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


def generate_event_feedback_payload(
    coach: GroqCoach | None,
    event_text: str,
    exercise: str,
    reps: int,
    target_sets: int,
    reps_per_set: int,
) -> dict:
    prompt = f"[EVENT] {event_text}"

    if coach is None:
        response_text = "Set complete. Take a short rest, then continue with control."
    else:
        response_text = coach.generate_response(
            prompt,
            exercise_type=exercise,
            reps=reps,
            target_sets=target_sets,
            reps_per_set=reps_per_set,
        )

    return {
        "response_text": response_text,
        "audio_bytes": synthesize_speech(response_text),
    }
    