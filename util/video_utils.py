"""OpenCV video I/O, with explicit timing and resource cleanup."""
import math
from pathlib import Path
import cv2

def read_video(video_path, *, return_metadata=False):
    path = Path(video_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Input video does not exist: {path}")
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise ValueError(f"OpenCV cannot open video: {path}")
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError(f"Video has invalid FPS: {fps}")
        frames = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frames.append(frame)
        if not frames:
            raise ValueError(f"Video contains no decodable frames: {path}")
        metadata = {
            "input_path": str(path), "fps": fps, "frame_count": len(frames),
            "width": int(frames[0].shape[1]), "height": int(frames[0].shape[0]),
            "duration_seconds": len(frames) / fps,
        }
        return (frames, metadata) if return_metadata else frames
    finally:
        cap.release()

def save_video(output_video_frames, output_video_path, fps=24):
    # Default retained only for compatibility with legacy callers.
    if not output_video_frames:
        raise ValueError("Cannot save an empty video")
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("FPS must be positive and finite")
    path = Path(output_video_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    height, width = output_video_frames[0].shape[:2]
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'XVID'), fps, (width, height))
    try:
        if not out.isOpened():
            raise OSError(f"Cannot create video writer: {path}")
        for frame in output_video_frames:
            if frame.shape[:2] != (height, width):
                raise ValueError("All video frames must have the same dimensions")
            out.write(frame)
    finally:
        out.release()
    if not path.is_file() or path.stat().st_size == 0:
        raise OSError(f"Video writer produced no output: {path}")
