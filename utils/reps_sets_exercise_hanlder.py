import re
from dataclasses import dataclass
from typing import Optional
from utils.var import EXERCISE_ALIASES, EXERCISE_OPTIONS, GOAL_TAG_RE, EXERCISE_TAG_RE, NUMBER_WORDS, EXERCISE_PATTERNS


def _canonical_key(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


@dataclass
class LlmControlSignals:
    response_text: str
    goal_sets: Optional[int] = None
    goal_reps: Optional[int] = None
    target_exercise: Optional[str] = None


def normalize_exercise_name(raw_name: str) -> Optional[str]:
    key = _canonical_key(raw_name)
    if key in EXERCISE_ALIASES:
        return EXERCISE_ALIASES[key]

    for option in EXERCISE_OPTIONS:
        if _canonical_key(option) == key:
            return option
    return None


def parse_llm_control_signals(raw_text: str) -> LlmControlSignals:
    text = (raw_text or "").strip()
    goal_match = GOAL_TAG_RE.search(text)
    exercise_match = EXERCISE_TAG_RE.search(text)

    goal_sets = int(goal_match.group(1)) if goal_match else None
    goal_reps = int(goal_match.group(2)) if goal_match else None

    target_exercise = None
    if exercise_match:
        target_exercise = normalize_exercise_name(exercise_match.group(1).strip())

    # Hide internal tags from TTS and UI.
    cleaned = GOAL_TAG_RE.sub("", text)
    cleaned = EXERCISE_TAG_RE.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    return LlmControlSignals(
        response_text=cleaned or "Keep going with controlled movement and steady breathing.",
        goal_sets=goal_sets,
        goal_reps=goal_reps,
        target_exercise=target_exercise,
    )


def _word_to_number(token: str) -> Optional[int]:
    value = (token or "").strip().lower()
    if not value:
        return None
    if value.isdigit():
        return int(value)
    return NUMBER_WORDS.get(value)


def _extract_named_number(text: str, label: str) -> Optional[int]:
    pattern = re.compile(rf"\b(\d+|{'|'.join(NUMBER_WORDS.keys())})\s+{label}\b", re.IGNORECASE)
    match = pattern.search(text)
    if not match:
        return None
    return _word_to_number(match.group(1))


def extract_control_signals_from_text(text: str) -> dict:
    spoken = (text or "").strip()
    if not spoken:
        return {
            "goal_sets": None,
            "goal_reps": None,
            "target_exercise": None,
        }

    target_exercise = None
    for exercise_name, pattern in EXERCISE_PATTERNS.items():
        if pattern.search(spoken):
            target_exercise = exercise_name
            break

    goal_sets = None
    goal_reps = None

    compact = spoken.lower().replace("-", " ")
    
    first_pattern = re.search(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\s+sets?\s*(?:of|x|by)?\s*(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\s+reps?\b",
        compact,
        re.IGNORECASE,
    )
    
    second_pattern = re.search(
        r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\s+reps?\s*(?:for|x|by)?\s*(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)\s+sets?\b",
        compact,
        re.IGNORECASE,
    )

    if first_pattern:
        goal_sets = _word_to_number(first_pattern.group(1))
        goal_reps = _word_to_number(first_pattern.group(2))
    elif second_pattern:
        goal_reps = _word_to_number(second_pattern.group(1))
        goal_sets = _word_to_number(second_pattern.group(2))
    else:
        goal_sets = _extract_named_number(compact, "sets?")
        goal_reps = _extract_named_number(compact, "reps?")

    if isinstance(goal_sets, int) and goal_sets <= 0:
        goal_sets = None
    if isinstance(goal_reps, int) and goal_reps <= 0:
        goal_reps = None

    return {
        "goal_sets": goal_sets,
        "goal_reps": goal_reps,
        "target_exercise": target_exercise,
    }


def compute_set_progress(total_reps: int, target_sets: int, reps_per_set: int) -> tuple[int, int, bool]:
    safe_reps = max(0, int(total_reps))
    safe_sets_target = max(0, int(target_sets))
    safe_reps_target = max(0, int(reps_per_set))

    if safe_sets_target == 0 or safe_reps_target == 0:
        return 0, safe_reps, False

    raw_completed = safe_reps // safe_reps_target
    completed_sets = min(raw_completed, safe_sets_target)

    if completed_sets >= safe_sets_target:
        reps_in_current_set = safe_reps_target
        workout_complete = True
    else:
        reps_in_current_set = safe_reps % safe_reps_target
        workout_complete = False

    return completed_sets, reps_in_current_set, workout_complete


def reset_goal_tracking(session_state) -> None:
    session_state.reps = 0
    session_state.target_sets = 0
    session_state.reps_per_set = 0
    session_state.sets_completed = 0
    session_state.current_set_reps = 0
    session_state.workout_complete = False
    session_state.last_notified_sets_completed = 0
    session_state.last_notified_workout_complete = False
    session_state.last_saved_sets_completed = 0
    session_state.set_cycle_started_at = 0.0


def sync_goal_progress(session_state) -> None:
    completed_sets, current_set_reps, workout_complete = compute_set_progress(
        total_reps=int(session_state.get("reps", 0)),
        target_sets=int(session_state.get("target_sets", 0)),
        reps_per_set=int(session_state.get("reps_per_set", 0)),
    )
    session_state.sets_completed = completed_sets
    session_state.current_set_reps = current_set_reps
    session_state.workout_complete = workout_complete


def apply_voice_control_updates(session_state, signals: dict) -> bool:
    changed_exercise = False

    goal_sets = signals.get("goal_sets")
    goal_reps = signals.get("goal_reps")
    target_exercise = signals.get("target_exercise")

    if isinstance(goal_sets, int) and goal_sets > 0:
        session_state.target_sets = goal_sets
    if isinstance(goal_reps, int) and goal_reps > 0:
        session_state.reps_per_set = goal_reps

    if isinstance(target_exercise, str) and target_exercise in EXERCISE_OPTIONS:
        if session_state.get("exercise_type") != target_exercise:
            # Do not mutate widget-backed key after widget is instantiated.
            session_state._pending_exercise_type = target_exercise
            changed_exercise = True

    return changed_exercise
