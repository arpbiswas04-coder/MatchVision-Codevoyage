"""Browser conversion, confined media lookup and public result projection."""
import logging
from pathlib import Path
import re
import shutil
import subprocess
from uuid import uuid4

from .storage import safe_file

logger = logging.getLogger(__name__)
HEATMAP_NAME = re.compile(r"(?:ball|player_[0-9]+|team_[0-9]+)\.png")
HIGHLIGHT_NAME = re.compile(r"clip_[0-9a-f]{32}\.(?:mp4|avi)")


def media_file(directory, kind, name=None):
    if kind == "video":
        if name not in ("output_video.mp4", "output_video.avi"):
            raise ValueError("Invalid video name")
        target = safe_file(directory, name)
    else:
        pattern = {"heatmaps": HEATMAP_NAME, "highlights": HIGHLIGHT_NAME}.get(kind)
        if pattern is None or not isinstance(name, str) or not pattern.fullmatch(name):
            raise ValueError("Invalid media name")
        folder = safe_file(directory, kind)
        target = safe_file(folder, name)
        target.relative_to(Path(directory).resolve())
    if not target.is_file():
        raise FileNotFoundError("Requested media is unavailable")
    return target


def convert_browser_video(directory, timeout):
    """Preserve the working AVI; conversion failure only changes media availability."""
    temporary = None
    try:
        source = media_file(directory, "video", "output_video.avi")
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return {"status": "unavailable", "reason": "FFmpeg is not available on PATH"}
        destination = safe_file(directory, "output_video.mp4")
        temporary = safe_file(directory, f".browser_{uuid4().hex}.mp4")
        subprocess.run(
            [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
             "-protocol_whitelist", "file,pipe", "-i", str(source), "-map", "0:v:0",
             "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", str(temporary)],
            shell=False, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise OSError("Browser encoder produced no video")
        temporary.rename(destination)
        return {"status": "available", "reason": None}
    except Exception:
        logger.exception("Optional browser video conversion failed")
        return {"status": "failed", "reason": "Browser conversion failed; AVI may still be downloaded"}
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not clean temporary browser video", exc_info=True)


def public_results(result, analysis_id, directory, conversion):
    """Preserve analytics while replacing filesystem references with registered URLs."""
    base = f"/api/matches/{analysis_id}"
    path_urls = {}
    media = {"video": {"browser_available": False, "url": None, "download_url": None,
                       "conversion": conversion}, "heatmaps": [], "highlights": []}

    def register(path, url):
        path_urls[str(path)] = url
        path_urls[path.as_posix()] = url
        path_urls[path.relative_to(directory).as_posix()] = url

    for name in ("output_video.avi", "output_video.mp4"):
        try:
            path = media_file(directory, "video", name)
        except (OSError, ValueError):
            continue
        register(path, base + "/video" + ("?download=true" if name.endswith(".avi") else ""))
        media["video"]["download_url"] = base + "/video?download=true"
        if name.endswith(".mp4"):
            media["video"].update(browser_available=True, url=base + "/video")

    for kind, pattern in (("heatmaps", HEATMAP_NAME), ("highlights", HIGHLIGHT_NAME)):
        try:
            folder = safe_file(directory, kind)
            if not folder.is_dir():
                continue
            for candidate in sorted(folder.iterdir()):
                if not pattern.fullmatch(candidate.name):
                    continue
                try:
                    path = media_file(directory, kind, candidate.name)
                except (OSError, ValueError):
                    continue
                url = f"{base}/{kind}/{candidate.name}"
                register(path, url)
                item = {"name": candidate.name, "url": url}
                if kind == "highlights":
                    item["browser_playable"] = candidate.suffix == ".mp4"
                media[kind].append(item)
        except (OSError, ValueError):
            logger.warning("Could not enumerate optional %s", kind, exc_info=True)

    def project(value, key=""):
        if isinstance(value, dict):
            return {field: project(child, field) for field, child in value.items()
                    if field not in ("input_path", "output_directory")}
        if isinstance(value, list):
            return [project(child) for child in value]
        if isinstance(value, str):
            if value in path_urls:
                return path_urls[value]
            if key == "analysis_json":
                return base + "/results"
            if key.endswith("_path") or key == "output_video":
                return None
            # Local error messages may embed paths, not just consist of a path.
            if (re.search(r"[A-Za-z]:[\\/]|\\\\", value) or str(directory) in value
                    or re.search(r"(?:^|\s|[=\(])/(?!api/)[^\s]+", value)):
                return "Local diagnostic omitted; see the server log."
        return value

    public = project(result)
    public["media"] = media
    public["output_video"] = media["video"]["url"] or media["video"]["download_url"]
    public["artifacts"] = {"analysis_json": base + "/results", "annotated_video": public["output_video"]}
    return public

