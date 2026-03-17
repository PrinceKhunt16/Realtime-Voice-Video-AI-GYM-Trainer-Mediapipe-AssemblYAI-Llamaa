import os
import base64
import time
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from dotenv import load_dotenv
from streamlit_webrtc import webrtc_streamer, WebRtcMode
from utils.video_processor import ExerciseVideoProcessor
from utils.css_func import load_css, inject_local_font
from utils.session_state import initialize_session_state
from utils.matrix_queue import drain_metrics_queue
from utils.var import METRICS_KEYS
from utils.audio_speech_to_text import AudioCommandPipeline
from utils.voice_pipeline import initialize_audio_state, update_command_context, start_voice_pipeline, stop_voice_pipeline, autoplay_audio, generate_event_feedback_payload
from utils.reps_sets_exercise_hanlder import apply_voice_control_updates, reset_goal_tracking, sync_goal_progress
from utils.database import init_db, add_exercise, get_user_exercises
from utils.auth import render_login_wall

load_dotenv()


def main():
    st.set_page_config(
        page_title="Real-time AI GYM Coach",
        page_icon="🏋️‍♂️",
        layout="centered",
        initial_sidebar_state="expanded",
    )

    load_css(os.path.join(os.getcwd(), "assets", "style.css"))
    inject_local_font(os.path.join(os.getcwd(), "assets", "AdobeClean.otf"), "AdobeClean")

    init_db()

    if not render_login_wall():
        return

    initialize_session_state()
    initialize_audio_state()

    pending_exercise = st.session_state.get("_pending_exercise_type")
    if isinstance(pending_exercise, str) and pending_exercise:
        st.session_state["exercise_type"] = pending_exercise
        st.session_state._pending_exercise_type = None

    with st.sidebar:
        st.title("🏋️‍♂️ Apna AI Coach")

        if st.session_state.get("username"):
            st.caption(f"👤 {st.session_state.username}")
        
        st.caption("Real-time pose detection and form analysis")

        exercise = st.selectbox(
            "Please select exercise",
            options=[
                "Squats",
                "Push-ups",
                "Bicep Curls (Dumbbell)",
                "Shoulder Press",
                "Lunges",
            ],
            key="exercise_type",
        )

        st.metric("Reps Completed (Total)", st.session_state.reps)
        
        if st.session_state.reps_per_set > 0 and st.session_state.target_sets > 0:
            st.metric(
                "Current Set Reps",
                f"{st.session_state.current_set_reps}/{st.session_state.reps_per_set}",
            )
            st.metric(
                "Sets Completed",
                f"{st.session_state.sets_completed}/{st.session_state.target_sets}",
            )
        else:
            st.metric("Sets Completed", st.session_state.sets_completed)

        st.divider()
        st.subheader("Voice Coach")
        st.checkbox(
            "Enable Voice Coach (uses system mic)",
            key="voice_enabled",
            help="Captures mic via PyAudio and streams to AssemblyAI for transcription.",
        )

        if st.session_state.voice_enabled:
            if not os.getenv("ASSEMBLYAI_API_KEY"):
                st.warning("Missing ASSEMBLYAI_API_KEY: voice transcription will not start.")
            if not os.getenv("GROQ_API_KEY"):
                st.info("GROQ_API_KEY not set: coach responses use fallback mode, but transcript command parsing still works.")

        st.divider()

        if exercise == "Squats":
            st.subheader("Squat Metrics")
            st.metric("Knee Angle",   f"{st.session_state.knee_angle}°")
            st.metric("Back Angle",   f"{st.session_state.back_angle}°")
            st.metric("Depth Status", st.session_state.depth_status)

        elif exercise == "Push-ups":
            st.subheader("Push-up Metrics")
            st.metric("Elbow Angle",    f"{st.session_state.elbow_angle}°")
            st.metric("Body Alignment", st.session_state.body_alignment)
            st.metric("Hip Position",   st.session_state.hip_status)

        elif exercise == "Bicep Curls (Dumbbell)":
            st.subheader("Curl Metrics")
            st.metric("Elbow Angle",        f"{st.session_state.elbow_angle}°")
            st.metric("Shoulder Stability", st.session_state.shoulder_status)
            st.metric("Swing Detection",    st.session_state.swing_status)

        elif exercise == "Shoulder Press":
            st.subheader("Shoulder Press Metrics")
            st.metric("Elbow Angle",   f"{st.session_state.elbow_angle}°")
            st.metric("Arm Extension", st.session_state.extension_status)
            st.metric("Back Arch",     st.session_state.back_arch_status)

        elif exercise == "Lunges":
            st.subheader("Lunge Metrics")
            st.metric("Front Knee Angle", f"{st.session_state.front_knee_angle}°")
            st.metric("Torso Angle",      f"{st.session_state.torso_angle}°")
            st.metric("Balance Status",   st.session_state.balance_status)

        if st.button("New session", use_container_width=True):
            ctx = st.session_state.get("exercise-analysis")

            if ctx is not None:
                if hasattr(ctx, "video_processor") and ctx.video_processor:
                    try:
                        ctx.video_processor.reset_for_exercise(st.session_state.get("exercise_type", "Squats"))
                    except Exception:
                        pass
                if isinstance(ctx, str):
                    del st.session_state["exercise-analysis"]

            for key in METRICS_KEYS:
                if "angle" in key or "reps" in key or "sets" in key:
                    st.session_state[key] = 0
                elif key == "workout_complete":
                    st.session_state[key] = False
                else:
                    st.session_state[key] = "N/A"
            
            reset_goal_tracking(st.session_state)
            
            st.session_state.last_saved_sets_completed = 0
            st.session_state.set_cycle_started_at = time.time()
            st.rerun()

    st.title("Real-time AI GYM Coach")
    st.caption("Real-time pose detection and form correction by Voice and Video AI")

    ctx = webrtc_streamer(
        key="exercise-analysis",
        mode=WebRtcMode.SENDRECV,
        video_processor_factory=ExerciseVideoProcessor,
        rtc_configuration={
            "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
        },
        media_stream_constraints={
            "video": True,
            "audio": False,        
        },
        async_processing=True,
    )

    drain_metrics_queue(ctx)
    sync_goal_progress(st.session_state)

    current_exercise = st.session_state.get("exercise_type", "Squats")
    
    if st.session_state.get("last_exercise_type") != current_exercise:
        if ctx is not None and not isinstance(ctx, str) and hasattr(ctx, "video_processor") and ctx.video_processor:
            try:
                ctx.video_processor.reset_for_exercise(current_exercise)
            except Exception:
                pass

        st.session_state.reps = 0
        st.session_state.last_notified_sets_completed = 0
        st.session_state.last_notified_workout_complete = False
        st.session_state.last_saved_sets_completed = 0
        st.session_state.set_cycle_started_at = time.time()
        sync_goal_progress(st.session_state)
        st.session_state.last_exercise_type = current_exercise

    target_sets = int(st.session_state.get("target_sets", 0))
    reps_per_set = int(st.session_state.get("reps_per_set", 0))
    sets_completed = int(st.session_state.get("sets_completed", 0))
    last_saved_sets = int(st.session_state.get("last_saved_sets_completed", 0))

    if target_sets > 0 and reps_per_set > 0 and sets_completed > last_saved_sets:
        newly_completed = sets_completed - last_saved_sets
        now_ts = time.time()
        started_at = float(st.session_state.get("set_cycle_started_at", now_ts))
        elapsed = max(1, int(now_ts - started_at))
        per_set_time = max(1, int(elapsed / max(1, newly_completed)))
        user_id = st.session_state.get("user_id")

        if isinstance(user_id, int):
            try:
                add_exercise(
                    user_id=user_id,
                    exercise_name=current_exercise,
                    reps=reps_per_set * newly_completed,
                    sets=newly_completed,
                    time=per_set_time * newly_completed,
                )

                st.session_state.last_saved_sets_completed = sets_completed
                st.session_state.set_cycle_started_at = now_ts
            except Exception as exc:
                st.warning(f"Could not save workout progress: {exc}")

    update_command_context(
        coach=st.session_state.groq_coach,
        exercise=current_exercise,
        reps=int(st.session_state.get("reps", 0)),
        target_sets=int(st.session_state.get("target_sets", 0)),
        reps_per_set=int(st.session_state.get("reps_per_set", 0)),
    )

    stream_active = bool(
        ctx and ctx.state.playing and st.session_state.voice_enabled
    )

    prev_active = st.session_state._prev_stream_active

    if stream_active and not prev_active:
        try:
            start_voice_pipeline()
        except Exception as exc:
            st.warning(f"Voice pipeline could not start: {exc}")

    elif not stream_active and prev_active:
        stop_voice_pipeline()

    st.session_state._prev_stream_active = stream_active

    received_voice_payload = False
    
    if stream_active:
        pipeline: AudioCommandPipeline | None = st.session_state.audio_pipeline
        
        if pipeline is not None:
            payload = pipeline.pop_latest_response()
            
            if payload:
                received_voice_payload = True
                st.session_state.latest_transcript     = payload.get("transcript", "")
                st.session_state.latest_voice_response = payload.get("response_text", "")
                st.session_state.latest_audio_bytes    = payload.get("audio_bytes", b"")
                
                signals = payload.get("control_signals", {})
                exercise_changed = apply_voice_control_updates(st.session_state, signals)
                
                if exercise_changed:
                    st.session_state.reps = 0

                sync_goal_progress(st.session_state)
                
                if exercise_changed:
                    st.rerun()

    if stream_active and not received_voice_payload:
        last_notified_sets = int(st.session_state.get("last_notified_sets_completed", 0))
        workout_complete = bool(st.session_state.get("workout_complete", False))
        workout_complete_notified = bool(st.session_state.get("last_notified_workout_complete", False))
        event_text = None

        if workout_complete and not workout_complete_notified:
            event_text = "All planned sets are complete. Congratulate the user and suggest cool-down."

            st.session_state.last_notified_workout_complete = True
            st.session_state.last_notified_sets_completed = sets_completed
        elif target_sets > 0 and reps_per_set > 0 and sets_completed > last_notified_sets:
            event_text = (
                f"Set {sets_completed} complete out of {target_sets}. "
                "Give short encouragement and rest guidance."
            )

            st.session_state.last_notified_sets_completed = sets_completed

        if event_text:
            event_payload = generate_event_feedback_payload(
                coach=st.session_state.groq_coach,
                event_text=event_text,
                exercise=current_exercise,
                reps=int(st.session_state.get("reps", 0)),
                target_sets=target_sets,
                reps_per_set=reps_per_set,
            )

            st.session_state.latest_voice_response = event_payload.get("response_text", "")
            st.session_state.latest_audio_bytes = event_payload.get("audio_bytes", b"")

    if st.session_state.latest_transcript:
        st.info(f"🗣️ You said: {st.session_state.latest_transcript}")

    if st.session_state.latest_voice_response:
        st.success(f"🏋️ Coach: {st.session_state.latest_voice_response}")

    user_id = st.session_state.get("user_id")

    if isinstance(user_id, int):
        st.divider()
        st.subheader("Workout History")

        try:
            history_rows = get_user_exercises(user_id)

            if history_rows:
                table_data = [
                    {   
                        "Exercise": row["exercise_name"],
                        "Reps": row["reps"],
                        "Sets": row["sets"],
                        "Time (sec)": row["time"],
                        "Logged At": row["created_at"],
                    }
                    for row in history_rows
                ]

                df = pd.DataFrame(table_data)
                df.index = df.index + 1

                st.table(df, border="horizontal")
            else:
                st.caption("No saved sets yet. Complete a set to add a record.")
        except Exception as exc:
            st.warning(f"Could not load workout history: {exc}")

    if st.session_state.latest_audio_bytes:
        autoplay_audio(st.session_state.latest_audio_bytes)
        st.session_state.latest_audio_bytes = b""

    if ctx and ctx.state.playing:
        time.sleep(0.5)
        st.rerun()


font_path = os.path.join(os.getcwd(), "assets", "AdobeClean.otf")

with open(font_path, "rb") as f:
    encoded_font = base64.b64encode(f.read()).decode()

components.html(f"""
<script>
(function patchWebRTCStyles() {{
    function injectIntoIframe(iframe) {{
        try {{
            const doc = iframe.contentDocument || iframe.contentWindow.document;
            if (!doc || !doc.head) return;
            if (doc.head.querySelector('#webrtc-custom-styles')) return;
            const style = doc.createElement('style');
            style.id = 'webrtc-custom-styles';
            style.textContent = `
                @font-face {{
                    font-family: 'AdobeClean';
                    src: url('data:font/otf;base64,{encoded_font}') format('opentype');
                    font-weight: 100 900;
                    font-style: normal;
                }}
                .MuiButtonBase-root,
                .MuiButton-root,
                .MuiButton-contained,
                .MuiButton-text {{
                    border-radius: 0 !important;
                    font-family: 'AdobeClean', sans-serif !important;
                    letter-spacing: 0.05em !important;
                }}
                ... rest of your styles ...
            `;
            doc.head.appendChild(style);
        }} catch (e) {{
            console.warn('[patcher] could not inject:', e);
        }}
    }}

    function findAndPatch() {{
        const parentDoc = window.parent.document;
        const iframes = parentDoc.querySelectorAll('iframe');
        iframes.forEach(iframe => {{
            if (iframe.src && iframe.src.includes('webrtc')) {{
                if (iframe.contentDocument && iframe.contentDocument.readyState === 'complete') {{
                    injectIntoIframe(iframe);
                }} else {{
                    iframe.addEventListener('load', () => injectIntoIframe(iframe));
                }}
            }}
        }});
    }}

    findAndPatch();
    const observer = new MutationObserver(findAndPatch);
    observer.observe(window.parent.document.body, {{ childList: true, subtree: true }});
}})();
</script>
""", height=0)


if __name__ == "__main__":
    main()
