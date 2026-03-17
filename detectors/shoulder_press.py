"""Shoulder Press exercise detector using MediaPipe pose landmarks."""

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


class ShoulderPressDetector(BaseExercise):
    """Detects Shoulder Press repetitions and calculates form metrics.

    Landmarks used (MediaPipe Pose indices):
      - LEFT_SHOULDER  : 11
      - LEFT_ELBOW     : 13
      - LEFT_WRIST     : 15
      - RIGHT_SHOULDER : 12
      - RIGHT_ELBOW    : 14
      - RIGHT_WRIST    : 16
      - LEFT_HIP       : 23
      - RIGHT_HIP      : 24

    Rep logic:
      - stage becomes "up"   when elbow_angle > UP_THRESHOLD   (arms extended overhead)
      - stage becomes "down" when elbow_angle < DOWN_THRESHOLD (elbows at 90°, start pos)
      - rep is counted on the down → up → down cycle (counted on descent)
    """

    UP_THRESHOLD   = 160   # degrees — arms fully extended overhead
    DOWN_THRESHOLD = 90    # degrees — elbows at roughly 90° (start/rack position)

    # Back arch: hip should not push significantly forward relative to shoulder
    ARCH_TOLERANCE = 0.08   # normalised units — forward hip displacement

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

        # Choose the more visible arm
        left_vis  = lm[13].visibility
        right_vis = lm[14].visibility
        if left_vis >= right_vis:
            shoulder_idx, elbow_idx, wrist_idx = 11, 13, 15
            hip_idx = 23
        else:
            shoulder_idx, elbow_idx, wrist_idx = 12, 14, 16
            hip_idx = 24

        # Elbow Angle (shoulder → elbow → wrist)
        elbow_angle = _calculate_angle(
            get_point(shoulder_idx),
            get_point(elbow_idx),
            get_point(wrist_idx),
        )

        # Rep Counting 
        min_visibility = 0.7
        key_landmarks_visible = (
            lm[shoulder_idx].visibility > min_visibility and
            lm[elbow_idx].visibility > min_visibility and
            lm[wrist_idx].visibility > min_visibility
        )
        
        if key_landmarks_visible:
            if elbow_angle > self.UP_THRESHOLD:
                self.stage = "up"
            if elbow_angle < self.DOWN_THRESHOLD and self.stage == "up":
                self.stage = "down"
                self.reps += 1

        # Arm Extension Status
        if elbow_angle >= self.UP_THRESHOLD:
            extension_status = "FULL EXTENSION ✓"
        elif elbow_angle >= 130:
            extension_status = "NEARLY EXTENDED"
        elif elbow_angle >= self.DOWN_THRESHOLD:
            extension_status = "PRESSING"
        else:
            extension_status = "START POSITION"

        # Back Arch Detection
        # Compare shoulder midpoint x to hip midpoint x.
        # During overhead press, leaning back pushes hips forward (camera-side).
        shoulder_x = lm[shoulder_idx].x
        hip_x      = lm[hip_idx].x
        hip_forward = hip_x - shoulder_x   # positive = hip further from camera

        # Back angle using shoulder → hip → knee
        knee_idx = 25 if hip_idx == 23 else 26
        back_angle = _calculate_angle(
            get_point(shoulder_idx),
            get_point(hip_idx),
            get_point(knee_idx),
        )

        if back_angle >= 160:
            back_arch_status = "Neutral ✓"
        elif back_angle >= 140:
            back_arch_status = "Slight Arch"
        else:
            back_arch_status = "Excessive Arch"

        return {
            "reps": self.reps,
            "elbow_angle": int(elbow_angle),
            "extension_status": extension_status,
            "back_arch_status": back_arch_status,
        }
