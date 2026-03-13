import os
import importlib
from typing import Optional
from utils.var import SYSTEM_PROMPT


class GroqCoach:
    """Small Groq wrapper used by the audio command pipeline."""

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

    def generate_response(
        self,
        user_text: str,
        exercise_type: str = "General",
        reps: int = 0,
        target_sets: int = 0,
        reps_per_set: int = 0,
    ) -> str:
        """Return a short coaching answer for the spoken user command."""
        cleaned = (user_text or "").strip()
        if not cleaned:
            return "I did not catch that. Please repeat your command."

        if self.client is None:
            return (
                f"Keep your {exercise_type.lower()} form controlled. "
                "Breathe steadily and maintain posture."
            )

        if target_sets > 0 and reps_per_set > 0:
            goal_line = f"Workout goal: {target_sets} sets x {reps_per_set} reps"
        else:
            goal_line = "Workout goal: NOT YET SET"

        user_prompt = (
            f"Exercise: {exercise_type}\n"
            f"Current reps: {reps}\n"
            f"{goal_line}\n"
            f"User command: {cleaned}\n"
            "Respond with a brief coaching instruction."
        )

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=100,
            )
            message = completion.choices[0].message.content if completion.choices else None
            return (message or "Stay focused and keep good form.").strip()
        except Exception:
            return "Focus on form: controlled movement, steady breathing, and full range of motion."
