"""
Proactive pose-based voice feedback engine.

Watches exercise metrics from the video processor and decides WHEN
to generate a spoken coaching cue via the LLM + TTS pipeline.

There is NO speech-to-text / microphone involved.
The engine is called on every Streamlit rerun while the workout is active.
"""

import time
from typing import Optional


# Minimum seconds between two consecutive spoken cues so we don't
# overwhelm the user with constant talking.
DEFAULT_COOLDOWN_SECONDS = 9.0


class FeedbackEngine:
    """Stateful engine that throttles and triggers proactive AI coach cues.

    Usage in main.py:
        engine = FeedbackEngine(coach, synthesize_speech)
        # inside the rerun loop:
        result = engine.maybe_generate(metrics, reps, sets_completed, target_sets, reps_per_set, exercise)
        if result:
            text, audio = result
            st.session_state.latest_coach_text = text
            st.session_state.latest_audio_bytes = audio
    """

    def __init__(self, coach, synthesize_speech, cooldown: float = DEFAULT_COOLDOWN_SECONDS):
        self._coach = coach
        self._tts = synthesize_speech
        self._cooldown = cooldown
        self._last_fired_at: float = 0.0

        # Track milestones so we only fire once per event
        self._last_notified_sets: int = 0
        self._last_notified_reps_milestone: int = 0
        self._workout_complete_spoken: bool = False

    def reset(self) -> None:
        """Call when a new workout session starts."""
        self._last_fired_at = 0.0
        self._last_notified_sets = 0
        self._last_notified_reps_milestone = 0
        self._workout_complete_spoken = False

    def maybe_generate(
        self,
        metrics: dict,
        reps: int,
        sets_completed: int,
        target_sets: int,
        reps_per_set: int,
        exercise: str,
    ) -> Optional[tuple[str, bytes]]:
        """
        Evaluate current metrics and decide whether to speak a cue.

        Returns (text, audio_bytes) if a cue fires, otherwise None.
        Enforces the cooldown timer between cues.
        """
        now = time.monotonic()

        # --- Priority 1: Workout complete (fire once, ignores cooldown) ---
        if target_sets > 0 and sets_completed >= target_sets and not self._workout_complete_spoken:
            self._workout_complete_spoken = True
            self._last_fired_at = now
            hint = (
                f"The user just finished ALL {target_sets} sets of {exercise}. "
                "Congratulate them warmly and suggest a cool-down stretch."
            )
            return self._generate(exercise, metrics, reps, target_sets, reps_per_set, hint)

        # --- Priority 2: Set completed (fire once per set) ---
        if (
            target_sets > 0
            and sets_completed > self._last_notified_sets
            and sets_completed < target_sets  # workout-complete handled above
        ):
            self._last_notified_sets = sets_completed
            self._last_fired_at = now
            hint = (
                f"Set {sets_completed} of {target_sets} is complete. "
                "Give short encouragement and tell them to rest ~30 seconds before the next set."
            )
            return self._generate(exercise, metrics, reps, target_sets, reps_per_set, hint)

        # Cooldown guard for all remaining cue types
        if now - self._last_fired_at < self._cooldown:
            return None

        # --- Priority 3: Rep milestone every 5 reps ---
        if reps > 0 and reps % 5 == 0 and reps != self._last_notified_reps_milestone:
            self._last_notified_reps_milestone = reps
            self._last_fired_at = now
            hint = f"The user just hit {reps} reps. Give a short energetic encouragement."
            return self._generate(exercise, metrics, reps, target_sets, reps_per_set, hint)

        # --- Priority 4: Form correction based on exercise-specific metrics ---
        form_hint = self._detect_form_issue(exercise, metrics)
        if form_hint:
            self._last_fired_at = now
            return self._generate(exercise, metrics, reps, target_sets, reps_per_set, form_hint)

        # --- Priority 5: General encouragement (fires at cooldown boundary) ---
        if now - self._last_fired_at >= self._cooldown * 2:
            self._last_fired_at = now
            hint = "Briefly encourage the user to maintain good form and keep going."
            return self._generate(exercise, metrics, reps, target_sets, reps_per_set, hint)

        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_form_issue(self, exercise: str, metrics: dict) -> Optional[str]:
        """Return a one-line hint about a form problem, or None if form looks OK."""

        if exercise == "Squats":
            depth = metrics.get("depth_status", "")
            back_angle = metrics.get("back_angle", 180)
            if depth == "TOO HIGH":
                return "The user's squat is not deep enough — knees are not bending sufficiently."
            if isinstance(back_angle, (int, float)) and back_angle < 130:
                return "The user is leaning too far forward during the squat."

        elif exercise == "Push-ups":
            alignment = metrics.get("body_alignment", "")
            hip_status = metrics.get("hip_status", "")
            if alignment == "Poor Form":
                return "The user's body is not straight during the push-up."
            if hip_status == "SAGGING":
                return "The user's hips are sagging down during the push-up."
            if hip_status == "PIKED UP":
                return "The user's hips are too high — lower them to form a straight line."

        elif exercise == "Bicep Curls (Dumbbell)":
            swing = metrics.get("swing_status", "")
            shoulder = metrics.get("shoulder_status", "")
            if swing == "SWINGING":
                return "The user is swinging their torso during the curl — keep the body still."
            if shoulder == "ELBOW DRIFTING":
                return "The user's elbow is drifting away from their side during the curl."

        elif exercise == "Shoulder Press":
            back_arch = metrics.get("back_arch_status", "")
            extension = metrics.get("extension_status", "")
            if back_arch == "Excessive Arch":
                return "The user is arching their lower back excessively during the press."
            if back_arch == "Slight Arch":
                return "Slight back arch detected — encourage the user to brace their core."

        elif exercise == "Lunges":
            balance = metrics.get("balance_status", "")
            if balance == "OFF BALANCE":
                return "The user is losing balance during the lunge — feet should be hip-width apart."

        return None

    def _generate(
        self,
        exercise: str,
        metrics: dict,
        reps: int,
        target_sets: int,
        reps_per_set: int,
        hint: str,
    ) -> Optional[tuple[str, bytes]]:
        """Call LLM + TTS and return (text, audio_bytes). Returns None on failure."""
        try:
            text = self._coach.generate_pose_feedback(
                exercise=exercise,
                metrics=metrics,
                reps=reps,
                target_sets=target_sets,
                reps_per_set=reps_per_set,
                hint=hint,
            )
            audio = self._tts(text)
            print(f"[FeedbackEngine] cue fired: {text!r}")
            return text, audio
        except Exception as exc:
            print(f"[FeedbackEngine] error generating cue: {exc}")
            return None
