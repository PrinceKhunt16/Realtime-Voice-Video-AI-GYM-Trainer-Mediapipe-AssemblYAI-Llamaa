"""Lunge exercise detector using MediaPipe pose landmarks."""

import math
from core.base_exercise import BaseExercise


def _calculate_angle(a: tuple, b: tuple, c: tuple) -> float:
    """Calculate the angle at joint B formed by points A-B-C.

    All points are (x, y) tuples (normalised 0-1 from MediaPipe).
    Returns the angle in degrees (0-180).
    """
    ax, ay = a[0] - b[0], a[1] - b[1]
    cx, cy = c[0] - b[0], c[1] - b[1]
    dot = ax * cx + ay * cy
    mag_a = math.sqrt(ax ** 2 + ay ** 2)
    mag_c = math.sqrt(cx ** 2 + cy ** 2)
    if mag_a * mag_c == 0:
        return 0.0
    cos_angle = max(-1.0, min(1.0, dot / (mag_a * mag_c)))
    return math.degrees(math.acos(cos_angle))


class LungeDetector(BaseExercise):
    """Detects Lunge repetitions and calculates form metrics.

    Landmarks used (MediaPipe Pose indices):
      - LEFT_HIP       : 23
      - LEFT_KNEE      : 25
      - LEFT_ANKLE     : 27
      - RIGHT_HIP      : 24
      - RIGHT_KNEE     : 26
      - RIGHT_ANKLE    : 28
      - LEFT_SHOULDER  : 11
      - RIGHT_SHOULDER : 12

    Rep logic:
      The front knee is the one with the smaller (more bent) angle.
      - stage becomes "down" when front_knee_angle < DOWN_THRESHOLD
      - stage becomes "up"   when front_knee_angle > UP_THRESHOLD and was "down"
      - rep counted on the down → up transition
    """

    DOWN_THRESHOLD = 100   # degrees — deep lunge position
    UP_THRESHOLD   = 160   # degrees — standing / recovered

    # Torso should remain upright (shoulder → hip → knee angle)
    TORSO_UPRIGHT_MIN = 160   # degrees — considered upright
    TORSO_LEAN_MIN    = 140   # degrees — slight lean (acceptable)

    # Balance: shoulder midpoint should be roughly above hip midpoint (x-axis)
    BALANCE_TOLERANCE = 0.10  # normalised units

    def __init__(self):
        super().__init__()

    def reset(self) -> None:
        self.reps  = 0
        self.stage = None

    def process(self, landmarks) -> dict:
        """Process one frame's landmarks and return updated metrics."""

        lm = landmarks

        def get_point(idx: int) -> tuple:
            p = lm[idx]
            return (p.x, p.y)

        # Knee Angles
        left_knee_angle = _calculate_angle(
            get_point(23),  # left hip
            get_point(25),  # left knee
            get_point(27),  # left ankle
        )
        right_knee_angle = _calculate_angle(
            get_point(24),  # right hip
            get_point(26),  # right knee
            get_point(28),  # right ankle
        )

        # Front leg = the more bent knee (smaller angle)
        if left_knee_angle <= right_knee_angle:
            front_knee_angle = left_knee_angle
            front_hip_idx, front_knee_idx, front_ankle_idx = 23, 25, 27
            shoulder_idx_for_torso = 11
        else:
            front_knee_angle = right_knee_angle
            front_hip_idx, front_knee_idx, front_ankle_idx = 24, 26, 28
            shoulder_idx_for_torso = 12

        # Rep Counting - only count if key landmarks are clearly visible
        min_visibility = 0.7
        key_landmarks_visible = (
            lm[front_hip_idx].visibility > min_visibility and
            lm[front_knee_idx].visibility > min_visibility and
            lm[front_ankle_idx].visibility > min_visibility
        )
        
        if key_landmarks_visible:
            if front_knee_angle < self.DOWN_THRESHOLD:
                self.stage = "down"
            if front_knee_angle > self.UP_THRESHOLD and self.stage == "down":
                self.stage = "up"
                self.reps += 1

        # Torso Angle (shoulder → hip → knee of front leg)
        torso_angle = _calculate_angle(
            get_point(shoulder_idx_for_torso),
            get_point(front_hip_idx),
            get_point(front_knee_idx),
        )

        if torso_angle >= self.TORSO_UPRIGHT_MIN:
            torso_status = "UPRIGHT ✓"
        elif torso_angle >= self.TORSO_LEAN_MIN:
            torso_status = "SLIGHT LEAN"
        else:
            torso_status = "LEANING FORWARD"

        # Balance Status
        shoulder_mid_x = (lm[11].x + lm[12].x) / 2
        hip_mid_x      = (lm[23].x + lm[24].x) / 2
        lateral_offset = abs(shoulder_mid_x - hip_mid_x)

        if lateral_offset <= self.BALANCE_TOLERANCE:
            balance_status = "BALANCED ✓"
        else:
            balance_status = "OFF BALANCE"

        return {
            "reps": self.reps,
            "front_knee_angle": int(front_knee_angle),
            "torso_angle": int(torso_angle),
            "balance_status": balance_status,
        }
