import streamlit as st
import queue
from services.vision.exercise_video_processor import ExerciseVideoProcessor


def drain_metrics_queue(ctx):
    """Drain the video processor's result_queue and update session_state."""
    if ctx is None or isinstance(ctx, str) or not hasattr(ctx, "state") or not ctx.state.playing:
        return

    processor: ExerciseVideoProcessor | None = getattr(ctx, "video_processor", None)

    if processor is None:
        return

    # Sync exercise type from sidebar to processor
    processor.exercise = st.session_state.get("exercise_type", "Squats")

    # Drain all pending metrics (take the latest one)
    latest = None

    while True:
        try:
            latest = processor.result_queue.get_nowait()
        except queue.Empty:
            break

    if latest is None:
        return

    ex = latest.get("exercise_type", "")

    if ex == "Squats":
        st.session_state.reps = latest.get("reps", st.session_state.reps)
        st.session_state.knee_angle = latest.get("knee_angle", 0)
        st.session_state.back_angle = latest.get("back_angle", 0)
        st.session_state.depth_status = latest.get("depth_status", "N/A")

    elif ex == "Push-ups":
        st.session_state.reps = latest.get("reps", st.session_state.reps)
        st.session_state.elbow_angle = latest.get("elbow_angle", 0)
        st.session_state.body_alignment = latest.get("body_alignment", "N/A")
        st.session_state.hip_status = latest.get("hip_status", "N/A")

    elif ex == "Bicep Curls (Dumbbell)":
        st.session_state.reps = latest.get("reps", st.session_state.reps)
        st.session_state.elbow_angle = latest.get("elbow_angle", 0)
        st.session_state.shoulder_status = latest.get("shoulder_status", "N/A")
        st.session_state.swing_status = latest.get("swing_status", "N/A")

    elif ex == "Shoulder Press":
        st.session_state.reps = latest.get("reps", st.session_state.reps)
        st.session_state.elbow_angle = latest.get("elbow_angle", 0)
        st.session_state.extension_status = latest.get("extension_status", "N/A")
        st.session_state.back_arch_status = latest.get("back_arch_status", "N/A")

    elif ex == "Lunges":
        st.session_state.reps = latest.get("reps", st.session_state.reps)
        st.session_state.front_knee_angle = latest.get("front_knee_angle", 0)
        st.session_state.torso_angle = latest.get("torso_angle", 0)
        st.session_state.balance_status = latest.get("balance_status", "N/A")
