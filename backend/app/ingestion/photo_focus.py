"""Where to anchor a Band's photo when the site crops it: its focal point, from the faces in it.

The site shows a Band's photo cropped (`object-fit: cover`): from `sm` as a banner the column's width and at most
288px tall, on phones as a 64px circle (DESIGN.md, "Band photo"). Centred, those crops can cut off what matters, a
head most of all. So each stored photo gets a focal point, {"x": .., "y": ..} in percent, which the site applies as
CSS `object-position: x% y%`.

Faces are found by YuNet (OpenCV's cv2.FaceDetectorYN; the model is vendored in yunet/, MIT licence). The point is
the centre of all the confident faces' bounding box, pulled halfway toward the largest face. On each axis it's
then turned into the object-position that centres it in the tighter of the site's two crops (the circle crops a
landscape photo's sides; the banner, its top and bottom), kept so the faces stay whole in that crop (all of them if
they fit, else the largest), and within 0–100. A crop that fits the tighter one fits the looser one too, so a face
whole in one is whole in both. On an axis neither crop cuts, it's the point itself.

A photo without a face gets DEFAULT: centred across, a little above the middle, since heads tend to be in the top
part of a Band photo. The same image always gets the same point.
"""
from __future__ import annotations

import functools
import io
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

MODEL = Path(__file__).with_name("yunet") / "face_detection_yunet_2023mar.onnx"
DEFAULT = {"x": 50.0, "y": 35.0}
MIN_SCORE = 0.8             # YuNet's confidence; lower picks up patterns in crowds and stage lights
BACKGROUND_FACE = 0.4       # a face less than this fraction of the largest's width is in the background
BANNER_ASPECT = 672 / 288   # the banner at its widest: the 672px column, at most 288px (max-h-72) tall


@dataclass(frozen=True)
class Face:
    x: float
    y: float
    w: float
    h: float
    score: float


_lock = threading.Lock()


@functools.cache
def _detector():
    import cv2  # imported here: it's only needed when there's a photo to look at

    # OpenCV warns on every model load that its new DNN engine ignores the (default) target; nothing's wrong.
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    return cv2.FaceDetectorYN.create(str(MODEL), "", (320, 320), score_threshold=MIN_SCORE)


def detect_faces(image: Image.Image) -> list[Face]:
    """The confident faces in `image`, in pixels, largest first."""
    rgb = np.asarray(image.convert("RGB"))
    bgr = np.ascontiguousarray(rgb[:, :, ::-1])
    height, width = bgr.shape[:2]
    with _lock:  # one detector, sized per photo
        detector = _detector()
        detector.setInputSize((width, height))
        _, found = detector.detect(bgr)
    faces = []
    for row in found if found is not None else []:
        # Clip each box to the image: a face cut by the photo's edge reaches past it.
        x0, y0 = max(0.0, float(row[0])), max(0.0, float(row[1]))
        x1, y1 = min(float(width), float(row[0] + row[2])), min(float(height), float(row[1] + row[3]))
        if x1 > x0 and y1 > y0:
            faces.append(Face(x0, y0, x1 - x0, y1 - y0, float(row[-1])))
    return sorted(faces, key=lambda f: (-f.w * f.h, f.x, f.y))


def _axis(point: float, group: tuple[float, float], largest: tuple[float, float], visible: float) -> float:
    """The object-position (0–1) on one axis that centres `point` in a crop showing `visible` of the photo, keeping
    `group` (all the faces) whole in it if it fits, else `largest` (the largest face). All are fractions of the
    photo. A crop starts at position × (1 − visible), so a span [lo, hi] is whole for positions from
    (hi − visible) / (1 − visible) to lo / (1 − visible)."""
    if visible >= 1:
        return point  # neither crop cuts this axis
    position = (point - visible / 2) / (1 - visible)
    for lo, hi in (group, largest):
        if hi - lo <= visible:
            position = min(max(position, (hi - visible) / (1 - visible)), lo / (1 - visible))
            break
    return min(max(position, 0.0), 1.0)


def focus_for(faces: list[Face], width: int, height: int) -> dict[str, float]:
    """The focal point, as object-position percentages, of a `width` × `height` photo with these faces."""
    if not faces:
        return dict(DEFAULT)
    largest = max(faces, key=lambda f: (f.w * f.h, -f.x, -f.y))
    faces = [f for f in faces if f.w >= BACKGROUND_FACE * largest.w]

    def span(fs, start, size, total):
        return min(getattr(f, start) for f in fs) / total, max(getattr(f, start) + getattr(f, size) for f in fs) / total

    group_x, group_y = span(faces, "x", "w", width), span(faces, "y", "h", height)
    big_x, big_y = span([largest], "x", "w", width), span([largest], "y", "h", height)
    point_x = (sum(group_x) / 2 + sum(big_x) / 2) / 2
    point_y = (sum(group_y) / 2 + sum(big_y) / 2) / 2

    aspect = width / height
    visible_x = min(1.0, 1 / aspect)            # the circle crops a landscape photo's sides
    visible_y = min(1.0, aspect / BANNER_ASPECT)  # the banner crops top and bottom (more than the circle does)
    return {"x": round(100 * _axis(point_x, group_x, big_x, visible_x), 1),
            "y": round(100 * _axis(point_y, group_y, big_y, visible_y), 1)}


def photo_focus(image: Image.Image) -> dict[str, float]:
    """The focal point of a photo, as object-position percentages ({"x", "y"})."""
    return focus_for(detect_faces(image), image.width, image.height)


def photo_focus_of(data: bytes | Path | str) -> dict[str, float]:
    """The focal point of a stored photo, from its bytes or its file."""
    with Image.open(io.BytesIO(data) if isinstance(data, bytes) else data) as image:
        image.load()
        return photo_focus(image)
