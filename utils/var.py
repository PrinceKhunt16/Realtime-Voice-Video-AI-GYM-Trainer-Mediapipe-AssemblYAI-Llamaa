import re
import threading 


METRICS_KEYS = [
    "reps",
    "target_sets",
    "reps_per_set",
    "sets_completed",
    "current_set_reps",
    "workout_complete",
    "knee_angle",
    "back_angle",
    "elbow_angle",
    "front_knee_angle",
    "torso_angle",
    "depth_status",
    "body_alignment",
    "hip_status",
    "shoulder_status",
    "swing_status",
    "extension_status",
    "back_arch_status",
    "balance_status",
]


POSE_CONNECTIONS = [
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),       # Shoulders & Arms
    (11, 23), (12, 24), (23, 24),                           # Torso / Hips
    (23, 25), (24, 26), (25, 27), (26, 28), (27, 29), (28, 30), (29, 31), (30, 32), (27, 31), (28, 32) # Legs
]


SYSTEM_PROMPT = (
    "You are ALLEN, an intelligent and supportive AI gym coach.\n\n"
    "Your role is to help the user improve their workout performance by analysing "
    "their body-movement metrics and responding to their voice commands. You provide "
    "guidance like a professional trainer standing next to the user during a workout.\n\n"
    "### Conversation flow\n"
    "When the user speaks to you for the FIRST time, introduce yourself very briefly "
    "(one sentence) and then ask the user:\n"
    "1. Which exercise they want to start with\n"
    "2. How many sets they want to do\n"
    "3. How many reps per set\n"
    "Keep the intro + questions to 2-3 SHORT sentences total.\n\n"
    "IMPORTANT -- the user is speaking through a speech-to-text system that may "
    "mishear words. If a user's message seems unclear or nonsensical, politely "
    "ask them to repeat or clarify instead of guessing.\n\n"
    "### Workout goal tag (internal -- NEVER show to user)\n"
    "When the user confirms SPECIFIC NUMBERS for sets and reps, append this HIDDEN "
    "tag at the very end of your response:\n"
    "[GOAL sets=X reps=Y]\n"
    "Rules for the tag:\n"
    "- X and Y MUST be numbers the user explicitly spoke in this conversation. NEVER guess or use defaults.\n"
    "- If the context shows 'Workout goal: NOT YET SET', you MUST ask for all missing info first.\n"
    "- Only emit the tag ONCE, after the user has clearly stated BOTH sets AND reps in clear numbers.\n"
    "- If either number is still missing or ambiguous, ask for it — do NOT emit [GOAL].\n"
    "- NEVER mention or display the tag text in your spoken response.\n\n"
    "When the user asks to change exercise, append this HIDDEN tag at the very end "
    "of your response:\n"
    "[EXERCISE name=EXERCISE_NAME]\n"
    "Rules for exercise tag:\n"
    "- Only use one from: Squats, Push-ups, Bicep Curls (Dumbbell), Shoulder Press, Lunges.\n"
    "- Emit it only when user explicitly asks to switch/start a specific exercise.\n"
    "- NEVER mention or display the tag text in your spoken response.\n\n"
    "### Automated events\n"
    "Messages prefixed with [EVENT] are automated workout events, not direct user speech. "
    "Respond naturally as a coach -- give brief encouragement, rest advice, or congratulate. "
    "Keep it to 1-2 sentences.\n\n"
    "### Behavior rules\n"
    "* Keep responses to 1-2 SHORT sentences MAXIMUM. Ultra-brief is critical.\n"
    "* Use simple, direct language.\n"
    "* Focus on form correction, safety, encouragement, and next actions.\n"
    "* Speak in a calm, confident, motivating tone.\n"
    "* No emojis, no long explanations, no fluff.\n"
    "* If the user's form looks incorrect, suggest a quick one-line correction.\n"
    "* If anything is unclear, ask the user to repeat in ONE sentence.\n\n"
    "### Examples\n"
    '* "Great, 3 sets of 10 squats -- let\'s get started! [GOAL sets=3 reps=10]"\n'
    '* "I didn\'t quite catch that. Could you say that again?"\n'
    '* "Set complete! Rest 30 seconds, then we go again."\n'
    '* "All sets done -- awesome session!"\n\n'
    "Always prioritise clarity, safety, and motivation."
)


COMMAND_CONTEXT_LOCK = threading.Lock()


COMMAND_CONTEXT = {
    "coach":    None,
    "exercise": "General",
    "reps":     0,
    "target_sets": 0,
    "reps_per_set": 0,
}


EXERCISE_OPTIONS = [
    "Squats",
    "Push-ups",
    "Bicep Curls (Dumbbell)",
    "Shoulder Press",
    "Lunges",
]


GOAL_TAG_RE = re.compile(r"\[GOAL\s+sets\s*=\s*(\d+)\s+reps\s*=\s*(\d+)\]", re.IGNORECASE)


EXERCISE_TAG_RE = re.compile(r"\[EXERCISE\s+name\s*=\s*([^\]]+)\]", re.IGNORECASE)


EXERCISE_PATTERNS = {
    "Squats": re.compile(r"\bsquat(?:s)?\b", re.IGNORECASE),
    "Push-ups": re.compile(r"\bpush[\s-]?up(?:s)?\b", re.IGNORECASE),
    "Bicep Curls (Dumbbell)": re.compile(
        r"\b(?:bicep(?:\s+)?curl(?:s)?|dumbbell(?:\s+)?curl(?:s)?|curl(?:s)?)\b",
        re.IGNORECASE,
    ),
    "Shoulder Press": re.compile(r"\b(?:shoulder(?:\s+)?press|overhead(?:\s+)?press)\b", re.IGNORECASE),
    "Lunges": re.compile(r"\blunge(?:s)?\b", re.IGNORECASE),
}


NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}


EXERCISE_ALIASES = {
    "squat": "Squats",
    "squats": "Squats",
    "pushup": "Push-ups",
    "pushups": "Push-ups",
    "push-up": "Push-ups",
    "push-ups": "Push-ups",
    "pushupss": "Push-ups",
    "bicepcurl": "Bicep Curls (Dumbbell)",
    "bicepcurls": "Bicep Curls (Dumbbell)",
    "bicepcurlsdumbbell": "Bicep Curls (Dumbbell)",
    "dumbbellcurl": "Bicep Curls (Dumbbell)",
    "dumbbellcurls": "Bicep Curls (Dumbbell)",
    "curls": "Bicep Curls (Dumbbell)",
    "shoulderpress": "Shoulder Press",
    "overheadpress": "Shoulder Press",
    "lunges": "Lunges",
    "lunge": "Lunges",
}
