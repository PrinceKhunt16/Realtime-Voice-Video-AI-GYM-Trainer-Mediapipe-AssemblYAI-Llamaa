"""
Reps, sets and goal tracking utilities.

NOTE: Functions previously used by the STT pipeline (parse_llm_control_signals,
apply_voice_control_updates, extract_control_signals_from_text) have been
REMOVED as part of the architecture redesign. The workout plan is now set
via the sidebar UI before starting the session - voice commands are no longer used.
"""


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
