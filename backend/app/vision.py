"""Local MediaPipe Tasks frame analysis. Frames are processed in memory only."""
from dataclasses import dataclass
from pathlib import Path
import os


@dataclass
class FrameSignals:
    face_count: int
    gaze: str | None = None
    yaw: float | None = None
    pitch: float | None = None


class LocalFaceAnalyzer:
    def __init__(self):
        try:
            import cv2
            import mediapipe as mp

            self.cv2 = cv2
            self.mp = mp
            default_model = Path(__file__).resolve().parents[1] / "models" / "face_landmarker.task"
            self.model_path = Path(os.getenv("MEDIAPIPE_MODEL_PATH", default_model))
            if not self.model_path.is_file():
                raise FileNotFoundError(
                    f"Face model file is missing: {self.model_path}. Run setup.ps1 from the project root."
                )
            options = mp.tasks.vision.FaceLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(self.model_path)),
                running_mode=mp.tasks.vision.RunningMode.IMAGE,
                num_faces=3,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
            )
            self.landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)
        except Exception as exc:
            raise RuntimeError(f"Could not initialize local MediaPipe face analysis: {exc}") from exc

    def analyze(self, frame):
        import numpy as np

        rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
        result = self.landmarker.detect(image)
        faces = result.face_landmarks or []
        gaze = None
        yaw = pitch = None

        if faces:
            points = faces[0]
            # Iris positions are available in the 478-point model output.
            if len(points) > 473:
                left_ratio = (points[468].x - points[33].x) / max(0.001, points[133].x - points[33].x)
                right_ratio = (points[473].x - points[362].x) / max(0.001, points[263].x - points[362].x)
                ratio = (left_ratio + right_ratio) / 2
                # Use a broad neutral band so normal eye movement while reading
                # across the question is not treated as sustained looking away.
                if ratio < 0.22:
                    gaze = "left"
                elif ratio > 0.78:
                    gaze = "right"
                else:
                    gaze = "center"

            # Coarse head pose from six stable landmarks; not a calibrated
            # attention measurement. Angles are only used as review signals.
            h, w = frame.shape[:2]
            indices = [1, 152, 33, 263, 61, 291]
            image_points = np.array([[points[i].x * w, points[i].y * h] for i in indices], dtype=np.float64)
            model_points = np.array([
                (0.0, 0.0, 0.0), (0.0, -63.6, -12.5), (-43.3, 32.7, -26.0),
                (43.3, 32.7, -26.0), (-28.9, -28.9, -24.1), (28.9, -28.9, -24.1),
            ], dtype=np.float64)
            focal = float(w)
            camera = np.array([[focal, 0, w / 2], [0, focal, h / 2], [0, 0, 1]], dtype=np.float64)
            ok, rotation, _ = self.cv2.solvePnP(
                model_points, image_points, camera, np.zeros((4, 1)), flags=self.cv2.SOLVEPNP_ITERATIVE
            )
            if ok:
                matrix, _ = self.cv2.Rodrigues(rotation)
                angles, *_ = self.cv2.RQDecomp3x3(matrix)
                pitch, yaw = float(angles[0]), float(angles[1])

        return FrameSignals(face_count=len(faces), gaze=gaze, yaw=yaw, pitch=pitch)

    def close(self):
        self.landmarker.close()
