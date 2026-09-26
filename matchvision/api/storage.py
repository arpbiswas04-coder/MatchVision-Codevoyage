"""Constrained storage paths and lightweight upload validation."""
import math
import logging
from pathlib import Path
import re
from uuid import UUID

ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv"}


def validate_id(analysis_id):
    try:
        valid = isinstance(analysis_id, str) and UUID(analysis_id).hex == analysis_id
    except (ValueError, AttributeError):
        valid = False
    if not valid:
        raise ValueError("Invalid analysis identifier")
    return analysis_id


def analysis_directory(root, analysis_id):
    root = Path(root).resolve()
    target = (root / validate_id(analysis_id)).resolve()
    target.relative_to(root)
    if target == root:
        raise ValueError("Invalid analysis directory")
    return target


def safe_file(directory, name):
    if not name or Path(name).name != name or "/" in name or "\\" in name or ":" in name:
        raise ValueError("Invalid media name")
    root = Path(directory).resolve()
    target = (root / name).resolve()
    target.relative_to(root)
    if target == root:
        raise ValueError("Invalid file")
    return target


def clean_filename(filename):
    if not filename or not filename.strip():
        raise ValueError("A video filename is required")
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    extension = Path(basename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Supported video extensions: .mp4, .avi, .mov, .mkv")
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", Path(basename).stem).strip("._")[:100] or "video"
    return stem + extension, extension


def inspect_upload(path):
    # Only inspect metadata and decode the first frame. No model or full-video read.
    import cv2
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ValueError("The uploaded file could not be opened as a video")
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        ok, frame = capture.read()
        if not ok or frame is None or not frame.size:
            raise ValueError("The uploaded video has no readable first frame")
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("The uploaded video has invalid FPS metadata")
    except cv2.error:
        logging.getLogger(__name__).exception("OpenCV could not inspect the uploaded video")
        raise ValueError("The uploaded video could not be decoded") from None
    finally:
        capture.release()

