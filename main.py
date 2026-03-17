import os
import base64
import time
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from dotenv import load_dotenv
from streamlit_webrtc import webrtc_streamer, WebRtcMode
from services.vision.exercise_video_processor import ExerciseVideoProcessor
from services.ui.style_loader import load_css, inject_local_font
from services.state.session_defaults import initialize_session_state
from services.tracking.metrics_sync import drain_metrics_queue
from services.config.workout_config import METRICS_KEYS, EXERCISE_OPTIONS
from services.coaching.feedback_pipeline import initialize_voice_state, run_feedback_tick, reset_feedback_engine, autoplay_audio
from services.tracking.workout_progress import reset_goal_tracking, sync_goal_progress
from services.persistence.exercise_repository import init_db, add_exercise, get_user_exercises
from services.auth.login_gate import render_login_wall

load_dotenv()   


def _end_session():
    """Stop an active workout session and reset all metrics."""
    ctx = st.session_state.get("exercise-analysis")
    if ctx is not None and hasattr(ctx, "video_processor") and ctx.video_processor:
        try:
            ctx.video_processor.reset_for_exercise(
                st.session_state.get("exercise_type", "Squats")
            )
        except Exception:
            pass

    for key in METRICS_KEYS:
        if "angle" in key or "reps" in key or "sets" in key:
            st.session_state[key] = 0
        elif key == "workout_complete":
            st.session_state[key] = False
        else:
            st.session_state[key] = "N/A"

    reset_goal_tracking(st.session_state)
    reset_feedback_engine()

    st.session_state.workout_started = False
    st.session_state.last_saved_sets_completed = 0
    st.session_state.set_cycle_started_at = time.time()
    st.session_state.latest_coach_text = ""
    st.session_state.latest_audio_bytes = b""


def main():
    st.set_page_config(
        page_title="Real-time AI GYM Coach",
        page_icon="🏋️‍♂️",
        layout="centered",
        initial_sidebar_state="expanded",
    )

    load_css(os.path.join(os.getcwd(), "static", "style.css"))
    inject_local_font(os.path.join(os.getcwd(), "static", "AdobeClean.otf"), "AdobeClean")

    init_db()

    if not render_login_wall():
        return

    initialize_session_state()
    initialize_voice_state()

    workout_started = st.session_state.get("workout_started", False)

    with st.sidebar:
        st.title("🏋️‍♂️ Apna AI Coach")

        if st.session_state.get("username"):
            st.caption(f"👤 Login as {st.session_state.username}")

        st.divider()

        # Workout Plan Section (editable before start, locked during) 
        st.subheader("📋 Workout Plan")

        if not workout_started:
            # Let user configure their plan
            plan_exercise = st.selectbox(
                "Exercise",
                options=EXERCISE_OPTIONS,
                key="plan_exercise",
            )
            plan_sets = st.number_input(
                "Sets",
                min_value=1,
                max_value=20,
                step=1,
                key="plan_sets",
            )
            plan_reps = st.number_input(
                "Reps per Set",
                min_value=1,
                max_value=50,
                step=1,
                key="plan_reps",
            )

            st.markdown("")
            if st.button("▶️ Start Workout", use_container_width=True, type="primary"):
                # Lock in the plan and activate the session
                st.session_state.exercise_type = plan_exercise
                st.session_state.target_sets   = int(plan_sets)
                st.session_state.reps_per_set  = int(plan_reps)
                st.session_state.reps          = 0
                st.session_state.workout_started = True
                st.session_state.set_cycle_started_at = time.time()
                st.session_state.last_saved_sets_completed = 0
                st.session_state.last_notified_sets_completed = 0
                st.session_state.last_notified_workout_complete = False
                reset_feedback_engine()
                st.rerun()
        else:
            # Workout active — show locked plan summary
            ex = st.session_state.get("exercise_type", "Squats")
            ts = int(st.session_state.get("target_sets", 0))
            rps = int(st.session_state.get("reps_per_set", 0))
            st.info(f"**{ex}** — {ts} sets × {rps} reps")

            if st.button("⏹ End Session", use_container_width=True):
                _end_session()
                st.rerun()

        st.divider()

        # Live metrics (only while workout is active) 
        if workout_started:
            exercise = st.session_state.get("exercise_type", "Squats")
            reps = int(st.session_state.get("reps", 0))
            reps_per_set = int(st.session_state.get("reps_per_set", 0))
            target_sets = int(st.session_state.get("target_sets", 0))
            sets_completed = int(st.session_state.get("sets_completed", 0))
            current_set_reps = int(st.session_state.get("current_set_reps", 0))

            st.subheader("📊 Progress")
            st.metric("Total Reps", reps)

            if target_sets > 0 and reps_per_set > 0:
                st.metric(
                    "Current Set Reps",
                    f"{current_set_reps}/{reps_per_set}",
                )
                st.metric(
                    "Sets Completed",
                    f"{sets_completed}/{target_sets}",
                )

            st.divider()

            # Exercise-specific live metrics
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

    st.title("Real-time AI GYM Coach")
    st.caption("Real-time pose detection with proactive AI voice coaching")

    if not workout_started:
        # Pre-workout placeholder 
        st.markdown(
            """
            <div style="
                border: 10px dashed #444;
                border-radius: 0px;
                padding: 48px 32px;
                text-align: center;
                color: #888;
                margin-top: 32px;
            ">
                <h2 style="color:#ccc; margin-bottom:8px;">👈 Set your workout plan</h2>
                <p style="font-size:1.05rem;">
                    Choose your exercise, sets and reps in the sidebar,<br>
                    then click <strong>Start Workout</strong> to activate the camera and AI coach.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        # Active workout: camera + feedback
        current_exercise = st.session_state.get("exercise_type", "Squats")

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

        target_sets    = int(st.session_state.get("target_sets", 0))
        reps_per_set   = int(st.session_state.get("reps_per_set", 0))
        sets_completed = int(st.session_state.get("sets_completed", 0))
        last_saved_sets = int(st.session_state.get("last_saved_sets_completed", 0))

        # Auto-save completed sets to the database 
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

        # Proactive AI voice feedback tick
        if ctx and ctx.state.playing:
            # Build current metrics snapshot for the feedback engine
            current_metrics = {
                "exercise_type":   current_exercise,
                "reps":            int(st.session_state.get("reps", 0)),
                "depth_status":    st.session_state.get("depth_status", "N/A"),
                "knee_angle":      st.session_state.get("knee_angle", 0),
                "back_angle":      st.session_state.get("back_angle", 0),
                "body_alignment":  st.session_state.get("body_alignment", "N/A"),
                "hip_status":      st.session_state.get("hip_status", "N/A"),
                "elbow_angle":     st.session_state.get("elbow_angle", 0),
                "shoulder_status": st.session_state.get("shoulder_status", "N/A"),
                "swing_status":    st.session_state.get("swing_status", "N/A"),
                "extension_status":  st.session_state.get("extension_status", "N/A"),
                "back_arch_status":  st.session_state.get("back_arch_status", "N/A"),
                "front_knee_angle":  st.session_state.get("front_knee_angle", 0),
                "torso_angle":       st.session_state.get("torso_angle", 0),
                "balance_status":    st.session_state.get("balance_status", "N/A"),
            }

            run_feedback_tick(
                metrics=current_metrics,
                exercise=current_exercise,
                reps=int(st.session_state.get("reps", 0)),
                sets_completed=sets_completed,
                target_sets=target_sets,
                reps_per_set=reps_per_set,
            )

        # Coach feedback display
        coach_text = st.session_state.get("latest_coach_text", "")
        if coach_text:
            st.success(f"🏋️ Coach: {coach_text}")

        # Play queued audio
        if st.session_state.latest_audio_bytes:
            autoplay_audio(st.session_state.latest_audio_bytes)
            st.session_state.latest_audio_bytes = b""

        # Keep page refreshing so metrics and feedback stay live
        if ctx and ctx.state.playing:
            time.sleep(0.5)
            st.rerun()

    # WORKOUT HISTORY
    user_id = st.session_state.get("user_id")

    if isinstance(user_id, int):
        st.divider()
        st.subheader("Workout History")

        try:
            history_rows = get_user_exercises(user_id)

            if history_rows:
                table_data = [
                    {
                        "Exercise":   row["exercise_name"],
                        "Reps":       row["reps"],
                        "Sets":       row["sets"],
                        "Time (sec)": row["time"],
                        "Logged At":  row["created_at"],
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

font_path = os.path.join(os.getcwd(), "static", "AdobeClean.otf")

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
