"""Local face/figure detection for preview tile selection (Specification
§9.3-9.4, Tech Stack "Local Detection Models"): YuNet face detection, YOLOv8n
person detection, Laplacian blur scoring, and SFace face embeddings for
identity diversity — all via OpenCV / ONNX Runtime, no GPU required.

Every detector here is lazy-loaded and best-effort: if `opencv-python`/
`onnxruntime` aren't importable, or a model file is missing and can't be
downloaded, the corresponding `get_*()` function returns `None` and callers
fall back to blur-only frame ranking. This is a deliberate degradation path
(Tech Stack: "the backend must work, with reduced frame-selection quality,
if a model file is missing"), not an error condition.
"""

from __future__ import annotations

import logging
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

_YUNET_FILENAME = "face_detection_yunet_2023mar.onnx"
_YUNET_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
_SFACE_FILENAME = "face_recognition_sface_2021dec.onnx"
_SFACE_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_recognition_sface/face_recognition_sface_2021dec.onnx"
)
# No stable, official direct-download URL exists for a pre-exported
# YOLOv8n ONNX file; person detection is enabled by placing the file
# manually at `backend/models/yolov8n.onnx` (see docs/tech-stack.md).
_YOLOV8N_FILENAME = "yolov8n.onnx"

_PERSON_CLASS_ID = 0  # COCO class index for "person"
_DOWNLOAD_TIMEOUT_SECONDS = 20

_download_attempted: set[str] = set()


def _ensure_model(filename: str, url: str | None) -> Path | None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dest = MODELS_DIR / filename
    if dest.exists():
        return dest
    if url is None or filename in _download_attempted:
        return None

    _download_attempted.add(filename)
    try:
        with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response:
            data = response.read()
        tmp_dest = dest.with_suffix(dest.suffix + ".part")
        tmp_dest.write_bytes(data)
        tmp_dest.replace(dest)
        return dest
    except Exception as exc:  # noqa: BLE001 - any failure means "model unavailable"
        logger.warning("Could not download detection model %s: %s", filename, exc)
        return None


_face_detector = None
_face_detector_loaded = False
_face_recognizer = None
_face_recognizer_loaded = False
_person_session = None
_person_session_loaded = False


def get_face_detector():
    global _face_detector, _face_detector_loaded
    if _face_detector_loaded:
        return _face_detector
    _face_detector_loaded = True
    try:
        import cv2

        model_path = _ensure_model(_YUNET_FILENAME, _YUNET_URL)
        if model_path is None:
            return None
        _face_detector = cv2.FaceDetectorYN_create(str(model_path), "", (320, 320))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Face detector unavailable: %s", exc)
        _face_detector = None
    return _face_detector


def get_face_recognizer():
    global _face_recognizer, _face_recognizer_loaded
    if _face_recognizer_loaded:
        return _face_recognizer
    _face_recognizer_loaded = True
    try:
        import cv2

        model_path = _ensure_model(_SFACE_FILENAME, _SFACE_URL)
        if model_path is None:
            return None
        _face_recognizer = cv2.FaceRecognizerSF_create(str(model_path), "")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Face recognizer (identity diversity) unavailable: %s", exc)
        _face_recognizer = None
    return _face_recognizer


def get_person_session():
    global _person_session, _person_session_loaded
    if _person_session_loaded:
        return _person_session
    _person_session_loaded = True
    try:
        import onnxruntime

        model_path = _ensure_model(_YOLOV8N_FILENAME, None)
        if model_path is None:
            return None
        _person_session = onnxruntime.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Person detector unavailable: %s", exc)
        _person_session = None
    return _person_session


def detect_faces(image_bgr) -> list[dict]:
    """Returns `[{bbox: (x, y, w, h), confidence, landmarks_row}]`, sorted by
    confidence descending. `landmarks_row` is the raw YuNet detection row
    (bbox + 5 landmarks + score), needed by `face_embedding()`."""
    detector = get_face_detector()
    if detector is None:
        return []

    height, width = image_bgr.shape[:2]
    detector.setInputSize((width, height))
    _, faces = detector.detect(image_bgr)
    if faces is None:
        return []

    results = []
    for row in faces:
        x, y, w, h = row[0:4]
        confidence = float(row[14])
        results.append({"bbox": (float(x), float(y), float(w), float(h)), "confidence": confidence, "row": row})
    results.sort(key=lambda item: item["confidence"], reverse=True)
    return results


def face_embedding(image_bgr, face_row):
    """128-d SFace embedding for one YuNet detection row, or `None` if the
    recognizer isn't available."""
    recognizer = get_face_recognizer()
    if recognizer is None:
        return None
    try:
        aligned = recognizer.alignCrop(image_bgr, face_row)
        return recognizer.feature(aligned)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Face embedding failed: %s", exc)
        return None


def embedding_distance(embedding_a, embedding_b) -> float:
    """Cosine distance between two SFace embeddings (0 = identical face,
    higher = more different); falls back to a numpy cosine distance if the
    recognizer's own matcher isn't available."""
    recognizer = get_face_recognizer()
    if recognizer is not None:
        try:
            import cv2

            similarity = recognizer.match(embedding_a, embedding_b, cv2.FaceRecognizerSF_FR_COSINE)
            return 1.0 - float(similarity)
        except Exception:  # noqa: BLE001
            pass

    import numpy as np

    a, b = np.asarray(embedding_a).ravel(), np.asarray(embedding_b).ravel()
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
    return 1.0 - float(np.dot(a, b) / denom)


def _nms(boxes: list[tuple[float, float, float, float]], scores: list[float], iou_threshold: float = 0.5) -> list[int]:
    """Minimal greedy non-max suppression; boxes are (x1, y1, x2, y2)."""
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    keep: list[int] = []
    while order:
        current = order.pop(0)
        keep.append(current)
        remaining = []
        for i in order:
            xx1 = max(boxes[current][0], boxes[i][0])
            yy1 = max(boxes[current][1], boxes[i][1])
            xx2 = min(boxes[current][2], boxes[i][2])
            yy2 = min(boxes[current][3], boxes[i][3])
            inter = max(0.0, xx2 - xx1) * max(0.0, yy2 - yy1)
            area_a = (boxes[current][2] - boxes[current][0]) * (boxes[current][3] - boxes[current][1])
            area_b = (boxes[i][2] - boxes[i][0]) * (boxes[i][3] - boxes[i][1])
            iou = inter / (area_a + area_b - inter or 1.0)
            if iou <= iou_threshold:
                remaining.append(i)
        order = remaining
    return keep


def detect_persons(image_bgr, confidence_threshold: float = 0.4) -> list[dict]:
    """Returns `[{bbox: (x, y, w, h), confidence}]` for detected people,
    sorted by confidence descending. Empty if the model isn't available."""
    session = get_person_session()
    if session is None:
        return []

    import numpy as np
    import cv2

    input_size = 640
    height, width = image_bgr.shape[:2]
    scale = input_size / max(height, width)
    resized = cv2.resize(image_bgr, (max(1, round(width * scale)), max(1, round(height * scale))))
    canvas = np.zeros((input_size, input_size, 3), dtype=np.uint8)
    canvas[: resized.shape[0], : resized.shape[1]] = resized

    blob = cv2.dnn.blobFromImage(canvas, scalefactor=1 / 255.0, size=(input_size, input_size), swapRB=True)
    input_name = session.get_inputs()[0].name
    output = session.run(None, {input_name: blob})[0]

    # YOLOv8 ONNX output: (1, 4 + num_classes, num_boxes) -> transpose to (num_boxes, 4 + num_classes).
    predictions = output[0].transpose()

    boxes_xyxy: list[tuple[float, float, float, float]] = []
    scores: list[float] = []
    for pred in predictions:
        class_scores = pred[4:]
        class_id = int(np.argmax(class_scores))
        confidence = float(class_scores[class_id])
        if class_id != _PERSON_CLASS_ID or confidence < confidence_threshold:
            continue
        cx, cy, w, h = pred[0:4]
        boxes_xyxy.append((cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2))
        scores.append(confidence)

    if not boxes_xyxy:
        return []

    keep = _nms(boxes_xyxy, scores)
    results = []
    for i in keep:
        x1, y1, x2, y2 = boxes_xyxy[i]
        # Undo the letterbox scale back to original image coordinates.
        x1, y1, x2, y2 = x1 / scale, y1 / scale, x2 / scale, y2 / scale
        results.append({"bbox": (x1, y1, x2 - x1, y2 - y1), "confidence": scores[i]})
    results.sort(key=lambda item: item["confidence"], reverse=True)
    return results


def blur_score(image_bgr) -> float:
    """Laplacian variance sharpness heuristic; higher = sharper (less
    blurry). Requires only OpenCV, no model file."""
    import cv2

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())
