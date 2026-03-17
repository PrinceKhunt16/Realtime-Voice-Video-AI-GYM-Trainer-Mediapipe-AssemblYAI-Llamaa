import queue
import threading
import os
import av
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from streamlit_webrtc import VideoProcessorBase
from services.config.workout_config import POSE_CONNECTIONS
from detectors.squat import SquatDetector
from detectors.pushup import PushUpDetector
from detectors.bicep_curl import BicepCurlDetector
from detectors.shoulder_press import ShoulderPressDetector
from detectors.lunges import LungeDetector


class ExerciseVideoProcessor(VideoProcessorBase):
    def __init__(self):
        self.exercise_type: str = "Squats"
        self.result_queue: queue.Queue = queue.Queue(maxsize=5)
        self._lock = threading.Lock()

        # Initialize Tasks API PoseLandmarker
        model_path = os.path.join(os.getcwd(), "ml_models", "pose_landmarker.task")
        base_options = python.BaseOptions(model_asset_path=model_path)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            min_pose_detection_confidence=0.7,
            min_pose_presence_confidence=0.7,
            min_tracking_confidence=0.7,
            output_segmentation_masks=False,
        )
        self._landmarker = vision.PoseLandmarker.create_from_options(options)

        # Detectors
        self._detectors = {
            "Squats": SquatDetector(),
            "Push-ups": PushUpDetector(),
            "Bicep Curls (Dumbbell)": BicepCurlDetector(),
            "Shoulder Press": ShoulderPressDetector(),
            "Lunges": LungeDetector(),
        }
        self._frame_timestamp_ms = 0

    @property
    def exercise(self) -> str:
        with self._lock:
            return self.exercise_type

    @exercise.setter
    def exercise(self, value: str):
        with self._lock:
            self.exercise_type = value

    def reset(self) -> None:
        detector = self._detectors.get(self.exercise)
        if detector:
            detector.reset()
        while not self.result_queue.empty():
            try:
                self.result_queue.get_nowait()
            except queue.Empty:
                break

    def reset_for_exercise(self, exercise_name: str) -> None:
        detector = self._detectors.get(exercise_name)
        if detector:
            detector.reset()
        while not self.result_queue.empty():
            try:
                self.result_queue.get_nowait()
            except queue.Empty:
                break

    def _draw_skeleton(self, img, landmarks):
        h, w = img.shape[:2]
        for start_idx, end_idx in POSE_CONNECTIONS:
            p1 = landmarks[start_idx]
            p2 = landmarks[end_idx]
            if p1.visibility > 0.7 and p2.visibility > 0.7:
                cv2.line(
                    img,
                    (int(p1.x * w), int(p1.y * h)),
                    (int(p2.x * w), int(p2.y * h)),
                    (0, 255, 0), 8
                )
        for lm in landmarks:
            if lm.visibility > 0.7:
                cv2.circle(
                    img,
                    (int(lm.x * w), int(lm.y * h)),
                    8, (255, 0, 0), -1
                )

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        img = frame.to_ndarray(format="bgr24")
        img = cv2.flip(img, 1)

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        self._frame_timestamp_ms += int(1000 / 30)
        result = self._landmarker.detect_for_video(mp_image, self._frame_timestamp_ms)

        if result.pose_landmarks:
            landmarks = result.pose_landmarks[0]
            self._draw_skeleton(img, landmarks)

            with self._lock:
                ex_type = self.exercise_type

            detector = self._detectors.get(ex_type)
            if detector:
                try:
                    metrics = detector.process(landmarks)
                    metrics["exercise_type"] = ex_type

                    if ex_type == "Squats":
                        self._draw_squat_overlays(img, landmarks, metrics)
                    elif ex_type == "Push-ups":
                        self._draw_pushup_overlays(img, landmarks, metrics)
                    elif ex_type == "Bicep Curls (Dumbbell)":
                        self._draw_curl_overlays(img, landmarks, metrics)
                    elif ex_type == "Shoulder Press":
                        self._draw_press_overlays(img, landmarks, metrics)
                    elif ex_type == "Lunges":
                        self._draw_lunge_overlays(img, landmarks, metrics)

                    self.result_queue.put_nowait(metrics)
                except queue.Full:
                    pass
                except Exception:
                    pass
        else:
            cv2.putText(img, "NO POSE DETECTED ", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
            cv2.putText(img, "PLEASE FACE THE CAMERA", (30, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)

        return av.VideoFrame.from_ndarray(img, format="bgr24")  # type: ignore

    def _draw_squat_overlays(self, img, landmarks, metrics):
        h, w = img.shape[:2]
        status_text = f"DEPTH: {metrics['depth_status']}"
        cv2.putText(img, status_text, (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    def _draw_pushup_overlays(self, img, landmarks, metrics):
        h, w = img.shape[:2]
        status_text = f"BODY: {metrics['body_alignment']} | HIP: {metrics['hip_status']}"
        cv2.putText(img, status_text, (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    def _draw_curl_overlays(self, img, landmarks, metrics):
        h, w = img.shape[:2]
        status_text = f"SWING: {metrics['swing_status']}"
        cv2.putText(img, status_text, (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    def _draw_press_overlays(self, img, landmarks, metrics):
        h, w = img.shape[:2]
        status_text = f"EXT: {metrics['extension_status']} | BACK: {metrics['back_arch_status']}"
        cv2.putText(img, status_text, (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    def _draw_lunge_overlays(self, img, landmarks, metrics):
        h, w = img.shape[:2]
        status_text = f"BALANCE: {metrics['balance_status']}"
        cv2.putText(img, status_text, (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
