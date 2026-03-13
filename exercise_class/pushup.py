"""Push-up exercise detector using MediaPipe pose landmarks."""

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


class PushUpDetector(BaseExercise):
    """Detects push-up repetitions and calculates form metrics.

    Landmarks used (MediaPipe Pose indices):
      - LEFT_SHOULDER  : 11
      - LEFT_ELBOW     : 13
      - LEFT_WRIST     : 15
      - RIGHT_SHOULDER : 12
      - RIGHT_ELBOW    : 14
      - RIGHT_WRIST    : 16
      - LEFT_HIP       : 23
      - RIGHT_HIP      : 24
      - LEFT_ANKLE     : 27
      - RIGHT_ANKLE    : 28

    Rep logic:
      - stage becomes "down" when elbow_angle < DOWN_THRESHOLD (chest near floor)
      - stage becomes "up"   when elbow_angle > UP_THRESHOLD   (arms extended)
      - rep is counted on the down → up transition
    """

    DOWN_THRESHOLD = 90    # degrees — elbows bent, chest near floor
    UP_THRESHOLD   = 160   # degrees — arms extended

    # Body alignment: hip should be roughly between shoulder and ankle
    HIP_SAG_TOLERANCE = 0.08   # normalised units

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

        # Choose the more visible side
        left_vis  = lm[13].visibility   # left elbow
        right_vis = lm[14].visibility   # right elbow
        if left_vis >= right_vis:
            shoulder_idx, elbow_idx, wrist_idx = 11, 13, 15
            hip_idx, ankle_idx = 23, 27
        else:
            shoulder_idx, elbow_idx, wrist_idx = 12, 14, 16
            hip_idx, ankle_idx = 24, 28

        # Elbow Angle (shoulder → elbow → wrist)
        elbow_angle = _calculate_angle(
            get_point(shoulder_idx),
            get_point(elbow_idx),
            get_point(wrist_idx),
        )

        # Body Alignment (shoulder → hip → ankle should be nearly straight)
        body_angle = _calculate_angle(
            get_point(shoulder_idx),
            get_point(hip_idx),
            get_point(ankle_idx),
        )

        # Hip Position
        shoulder_y = lm[shoulder_idx].y
        ankle_y    = lm[ankle_idx].y
        hip_y      = lm[hip_idx].y
        
        # Interpolate expected hip y position on a straight line
        expected_hip_y = (shoulder_y + ankle_y) / 2
        hip_deviation  = hip_y - expected_hip_y   # positive => hip sagging down

        # Rep Counting - only count if key landmarks are clearly visible
        min_visibility = 0.7
        key_landmarks_visible = (
            lm[shoulder_idx].visibility > min_visibility and
            lm[elbow_idx].visibility > min_visibility and
            lm[wrist_idx].visibility > min_visibility and
            lm[hip_idx].visibility > min_visibility
        )
        
        if key_landmarks_visible:
            if elbow_angle < self.DOWN_THRESHOLD:
                self.stage = "down"
            if elbow_angle > self.UP_THRESHOLD and self.stage == "down":
                self.stage = "up"
                self.reps += 1

        # Body Alignment Status
        if body_angle > 160:
            body_alignment = "Straight ✓"
        elif body_angle > 140:
            body_alignment = "Slight Bend"
        else:
            body_alignment = "Poor Form"

        # Hip Status
        if abs(hip_deviation) <= self.HIP_SAG_TOLERANCE:
            hip_status = "LEVEL ✓"
        elif hip_deviation > self.HIP_SAG_TOLERANCE:
            hip_status = "SAGGING"
        else:
            hip_status = "PIKED UP"

        return {
            "reps": self.reps,
            "elbow_angle": int(elbow_angle),
            "body_alignment": body_alignment,
            "hip_status": hip_status,
        }
