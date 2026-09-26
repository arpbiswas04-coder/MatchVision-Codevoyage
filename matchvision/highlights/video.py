"""Local-file video probing/export with optional FFmpeg and an OpenCV fallback."""
import json
import logging
import math
import re
from pathlib import Path
import shutil
import subprocess
import time

from .paths import confined_path

logger = logging.getLogger(__name__)


def _positive(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def _run(arguments, timeout):
    return subprocess.run(arguments, shell=False, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, text=True, timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def probe_source(source_path, expected_metadata=None):
    import cv2
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError("Source video is unavailable")
    cap = cv2.VideoCapture(str(source))
    try:
        if not cap.isOpened():
            raise ValueError("Source video cannot be opened")
        fps = _positive(cap.get(cv2.CAP_PROP_FPS))
        frames = _positive(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if fps is None or frames is None or width <= 0 or height <= 0:
            raise ValueError("Source video has incomplete timing/dimension metadata")
    finally:
        cap.release()
    frame_count = int(frames)
    duration = frame_count / fps
    method = "opencv_frame_count_over_fps"
    expected_metadata = expected_metadata or {}
    # The original-upload path is an explicit argument, never taken from event JSON.
    # Catch obvious accidental selection of a different video without claiming identity verification.
    for key, actual in (("width", width), ("height", height)):
        if expected_metadata.get(key) is not None and expected_metadata[key] != actual:
            raise ValueError("Source dimensions do not match analysis metadata")
    expected_fps = _positive(expected_metadata.get("fps"))
    if expected_fps is not None and not math.isclose(expected_fps, fps, rel_tol=0.001):
        raise ValueError("Source FPS does not match analysis metadata")
    expected_duration = _positive(expected_metadata.get("duration_seconds"))
    if expected_duration is not None:
        duration = min(duration, expected_duration)
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            completed = _run([ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe",
                              "-show_entries", "format=duration:stream=codec_type,duration",
                              "-of", "json", str(source)], 10)
            info = json.loads(completed.stdout)
            stream = next((item for item in info.get("streams", []) if item.get("codec_type") == "video"), {})
            timestamp_duration = _positive(stream.get("duration")) or _positive(info.get("format", {}).get("duration"))
            if timestamp_duration is not None:
                duration = min(duration, timestamp_duration)
                method = "minimum_of_ffprobe_duration_and_decoded_or_opencv_duration"
        except Exception:
            logger.warning("Optional FFprobe duration probe failed; using OpenCV metadata", exc_info=True)
    return {"fps": fps, "frame_count": frame_count, "width": width, "height": height,
            "duration_seconds": duration, "duration_source": method}


def _validate_clip(path):
    import cv2
    if not path.is_file() or path.stat().st_size == 0:
        raise OSError("Encoder produced no clip")
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened() or not cap.read()[0]:
            raise OSError("Encoded clip is not decodable")
    finally:
        cap.release()


def _remove_owned_temp(run_directory, relative_path):
    try:
        path = confined_path(run_directory, relative_path)
        if path.is_file():
            path.unlink()
    except Exception:
        logger.warning("Could not clean an owned temporary highlight", exc_info=True)


def _ffmpeg(source, target, window, executable, timeout):
    # Output-side seek plus re-encoding avoids stream-copy keyframe padding.
    _run([executable, "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
          "-protocol_whitelist", "file,pipe", "-i", str(source),
          "-ss", f"{window['start']:.9f}", "-t", f"{window['end'] - window['start']:.9f}",
          "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "veryfast",
          "-crf", "23", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-movflags", "+faststart", str(target)], timeout)
    return {"start": window["start"], "end": window["end"],
            "audio_mode": "transcoded_if_present", "backend": "ffmpeg"}


def _opencv(source, target, window, info, timeout):
    import cv2
    fps = info["fps"]
    # Round inward so exported frame intervals cannot exceed the clamped window.
    first = max(0, math.ceil(window["start"] * fps - 1e-9))
    last = min(info["frame_count"], math.floor(window["end"] * fps + 1e-9))
    if last <= first:
        raise ValueError("Window contains no complete video frame")
    cap = cv2.VideoCapture(str(source))
    writer = None
    deadline = time.monotonic() + timeout
    try:
        if not cap.isOpened():
            raise OSError("Source video cannot be reopened")
        # Sequential decoding is portable and avoids inaccurate/keyframe-only seeks.
        for index in range(last):
            if time.monotonic() > deadline:
                raise TimeoutError("OpenCV highlight export exceeded its time budget")
            ok, frame = cap.read()
            if not ok:
                raise OSError("Source ended before requested highlight window")
            if index < first:
                continue
            if writer is None:
                height, width = frame.shape[:2]
                writer = cv2.VideoWriter(str(target), cv2.VideoWriter_fourcc(*"MJPG"), fps, (width, height))
                if not writer.isOpened():
                    raise OSError("OpenCV MJPG encoder is unavailable")
            writer.write(frame)
    finally:
        cap.release()
        if writer is not None:
            writer.release()
    return {"start": first / fps, "end": last / fps,
            "audio_mode": "not_available_opencv_video_only", "backend": "opencv"}


def export_clip(source_path, run_directory, clip_id, window, info, config):
    """Only generated local temp/final paths are used; return run-relative references."""
    source = Path(source_path).expanduser().resolve()
    if not isinstance(clip_id, str) or not re.fullmatch(r"[0-9a-f]{32}", clip_id):
        raise ValueError("Invalid generated clip identifier")
    modes = ["opencv"] if config.backend == "opencv" else ["ffmpeg"]
    if config.backend == "auto":
        modes.append("opencv")
    fallback = False
    for mode in modes:
        executable = shutil.which("ffmpeg") if mode == "ffmpeg" else None
        if mode == "ffmpeg" and executable is None:
            fallback = True
            continue
        extension = "mp4" if mode == "ffmpeg" else "avi"
        temporary = f"highlights/.clip_{clip_id}_{mode}.partial.{extension}"
        final = f"highlights/clip_{clip_id}.{extension}"
        owned = False
        try:
            target = confined_path(run_directory, temporary)
            destination = confined_path(run_directory, final)
            if target.exists() or destination.exists():
                raise FileExistsError("Generated highlight name already exists")
            owned = True
            if mode == "ffmpeg":
                exported = _ffmpeg(source, target, window, executable, config.export_timeout_seconds)
            else:
                exported = _opencv(source, target, window, info, config.export_timeout_seconds)
            _validate_clip(target)
            target.rename(destination)
            return {**exported, "video_path": final, "asset_id": f"clip_{clip_id}",
                    "fallback_used": fallback, "duration_seconds": exported["end"] - exported["start"]}
        except Exception:
            logger.warning("Highlight export via %s failed", mode, exc_info=True)
            if owned:
                _remove_owned_temp(run_directory, temporary)
            fallback = True
    raise OSError("All configured highlight encoders failed or are unavailable")


