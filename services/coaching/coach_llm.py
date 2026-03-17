import os
import importlib
from typing import Optional
from services.config.workout_config import SYSTEM_PROMPT


class GroqCoach:
    """Groq LLM wrapper for the proactive AI gym coach."""

    def __init__(self, api_key: Optional[str] = None, model: str = "llama-3.1-8b-instant"):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model
        self.client = None

        if self.api_key:
            try:
                groq_module = importlib.import_module("groq")
                self.client = groq_module.Groq(api_key=self.api_key)
            except Exception:
                self.client = None

    def generate_pose_feedback(
        self,
        exercise: str,
        metrics: dict,
        reps: int,
        target_sets: int,
        reps_per_set: int,
        hint: str = "",
    ) -> str:
        """
        Generate a single short coaching cue based on current pose metrics.

        This is the primary method used by FeedbackEngine for proactive,
        camera-driven feedback. The hint arg gives the LLM additional
        context about what triggered this cue (form issue / milestone / etc.).
        """
        if self.client is None:
            # Graceful fallback when no API key is set
            return self._fallback_cue(exercise, metrics)

        if target_sets > 0 and reps_per_set > 0:
            goal_line = f"Workout goal: {target_sets} sets × {reps_per_set} reps"
        else:
            goal_line = "Workout goal: not yet set"

        # Build a compact metrics summary for the LLM
        metrics_lines = "\n".join(
            f"  {k}: {v}" for k, v in metrics.items() if k != "exercise_type"
        )

        user_prompt = (
            f"Exercise: {exercise}\n"
            f"Reps completed: {reps}\n"
            f"{goal_line}\n"
            f"Current pose metrics:\n{metrics_lines}\n"
            f"Coaching context: {hint}\n"
            "Give ONE short coaching cue (1 sentence, spoken aloud to the athlete)."
        )

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=80,
            )
            message = completion.choices[0].message.content if completion.choices else None
            return (message or "Keep going — great form!").strip()
        except Exception:
            return self._fallback_cue(exercise, metrics)

    def _fallback_cue(self, exercise: str, metrics: dict) -> str:
        """Return a hardcoded cue when the LLM is unavailable."""
        fallbacks = {
            "Squats": "Drive through your heels and keep your chest up.",
            "Push-ups": "Keep your body in a straight line from head to heels.",
            "Bicep Curls (Dumbbell)": "Pin your elbows to your sides and curl with control.",
            "Shoulder Press": "Brace your core and press the weight straight overhead.",
            "Lunges": "Step forward with control and keep your torso upright.",
        }
        return fallbacks.get(exercise, "Great work — stay focused and keep good form.")
