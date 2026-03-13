"""Bicep Curl (Dumbbell) exercise detector using MediaPipe pose landmarks."""

import math
from abstract_class.base_exercise import BaseExercise


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


class BicepCurlDetector(BaseExercise):
    """Detects Bicep Curl repetitions and calculates form metrics.

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
      - stage becomes "up"   when elbow_angle < UP_THRESHOLD   (top of curl)
      - stage becomes "down" when elbow_angle > DOWN_THRESHOLD (arm extended)
      - rep is counted on the up → down transition
    """

    UP_THRESHOLD   = 50    # degrees — fully curled
    DOWN_THRESHOLD = 160   # degrees — arm fully extended

    # Elbow should not drift forward more than this relative to shoulder x
    ELBOW_DRIFT_TOLERANCE = 0.06    # normalised units

    # Body swing: torso tilt (shoulder → hip vertical) in degrees
    SWING_THRESHOLD = 15   # degrees from vertical indicates swing

    def __init__(self):
        super().__init__()
        self._shoulder_x_baseline: float | None = None

    def reset(self) -> None:
        self.reps  = 0
        self.stage = None
        self._shoulder_x_baseline = None

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
            opp_shoulder_idx = 12
            hip_idx = 23
        else:
            shoulder_idx, elbow_idx, wrist_idx = 12, 14, 16
            opp_shoulder_idx = 11
            hip_idx = 24

        # Elbow Angle (shoulder → elbow → wrist)
        elbow_angle = _calculate_angle(
            get_point(shoulder_idx),
            get_point(elbow_idx),
            get_point(wrist_idx),
        )

        # Rep Counting - only count if key landmarks are clearly visible
        min_visibility = 0.7
        key_landmarks_visible = (
            lm[shoulder_idx].visibility > min_visibility and
            lm[elbow_idx].visibility > min_visibility and
            lm[wrist_idx].visibility > min_visibility
        )
        
        if key_landmarks_visible:
            if elbow_angle < self.UP_THRESHOLD:
                self.stage = "up"
            if elbow_angle > self.DOWN_THRESHOLD and self.stage == "up":
                self.stage = "down"
                self.reps += 1

        # Shoulder Stability (elbow drift)
        shoulder_x = lm[shoulder_idx].x
        elbow_x    = lm[elbow_idx].x
        elbow_drift = abs(elbow_x - shoulder_x)

        if elbow_drift <= self.ELBOW_DRIFT_TOLERANCE:
            shoulder_status = "STABLE ✓"
        else:
            shoulder_status = "ELBOW DRIFTING"

        # Body Swing Detection (shoulder tilt vs hip)
        # Compute horizontal angle of torso lean using both shoulders vs hips
        left_shoulder_y  = lm[11].y
        right_shoulder_y = lm[12].y
        left_hip_y       = lm[23].y
        right_hip_y      = lm[24].y

        shoulder_mid_x = (lm[11].x + lm[12].x) / 2
        shoulder_mid_y = (left_shoulder_y + right_shoulder_y) / 2
        hip_mid_x      = (lm[23].x + lm[24].x) / 2
        hip_mid_y      = (left_hip_y + right_hip_y) / 2

        dx = shoulder_mid_x - hip_mid_x
        dy = shoulder_mid_y - hip_mid_y
        torso_angle_from_vertical = math.degrees(math.atan2(abs(dx), abs(dy))) if dy != 0 else 0.0

        if torso_angle_from_vertical <= self.SWING_THRESHOLD:
            swing_status = "NO SWING ✓"
        else:
            swing_status = "SWINGING"

        return {
            "reps": self.reps,
            "elbow_angle": int(elbow_angle),
            "shoulder_status": shoulder_status,
            "swing_status": swing_status,
        }
