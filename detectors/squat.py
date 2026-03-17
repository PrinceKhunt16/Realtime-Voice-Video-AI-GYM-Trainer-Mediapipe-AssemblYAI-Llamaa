"""Squat exercise detector using MediaPipe pose landmarks."""

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


class SquatDetector(BaseExercise):
    """Detects squat repetitions and calculates form metrics.

    Landmarks used (MediaPipe Pose indices):
      - LEFT_HIP      : 23
      - LEFT_KNEE     : 25
      - LEFT_ANKLE    : 27
      - LEFT_SHOULDER : 11
      - RIGHT_HIP     : 24
      - RIGHT_KNEE    : 26
      - RIGHT_ANKLE   : 28
      - RIGHT_SHOULDER: 12

    Rep logic:
      - stage becomes "down"  when knee_angle < 90°
      - stage becomes "up"    when knee_angle > 160°
      - rep is counted on the up→down→up transition
    """

    DOWN_THRESHOLD = 100    # degrees — full squat depth
    UP_THRESHOLD = 160     # degrees — standing position

    def __init__(self):
        super().__init__()

    def reset(self) -> None:
        self.reps = 0
        self.stage = None

    def process(self, landmarks) -> dict:
        """Process one frame's landmarks and return updated metrics."""

        lm = landmarks

        def get_point(idx: int) -> tuple:
            p = lm[idx]
            return (p.x, p.y)

        # Knee Angle (hip → knee → ankle)
        # Average left and right for robustness
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
        
        # Pick the side with the more visible landmark (lower visibility = more occluded)
        left_vis = lm[25].visibility
        right_vis = lm[26].visibility

        if left_vis >= right_vis:
            knee_angle = left_knee_angle
            hip_idx, knee_idx, ankle_idx, shoulder_idx = 23, 25, 27, 11
        else:
            knee_angle = right_knee_angle
            hip_idx, knee_idx, ankle_idx, shoulder_idx = 24, 26, 28, 12

        # Back Angle (shoulder → hip → knee)
        back_angle = _calculate_angle(
            get_point(shoulder_idx),
            get_point(hip_idx),
            get_point(knee_idx),
        )

        # Rep Counting - only count if key landmarks are clearly visible
        min_visibility = 0.7
        key_landmarks_visible = (
            lm[hip_idx].visibility > min_visibility and
            lm[knee_idx].visibility > min_visibility and
            lm[ankle_idx].visibility > min_visibility
        )
        
        if key_landmarks_visible:
            if knee_angle < self.DOWN_THRESHOLD:
                self.stage = "down"
            if knee_angle > self.UP_THRESHOLD and self.stage == "down":
                self.stage = "up"
                self.reps += 1

        # Depth Status
        if self.stage == "down":
            depth_status = "GOOD DEPTH ✓" if knee_angle <= self.DOWN_THRESHOLD else "TOO HIGH"
        elif self.stage == "up":
            depth_status = "STANDING"
        else:
            depth_status = "N/A"

        return {
            "reps": self.reps,
            "knee_angle": int(knee_angle),
            "back_angle": int(back_angle),
            "depth_status": depth_status,
        }
