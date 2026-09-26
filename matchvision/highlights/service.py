"""Optional media exports never invalidate the main analysis."""
import json
import logging
from uuid import uuid4

from .paths import confined_path, prepare_directory
from .planning import HighlightConfig, plan_highlights, select_events
from .video import export_clip, probe_source

logger = logging.getLogger(__name__)


def generate_highlights(events, input_video_path, run_directory, *, config=None,
                        annotated_video_path=None, video_metadata=None):
    result = {"highlights": [], "highlight_generation": {
        "status": "failed", "source": None, "directory": None, "manifest_path": None,
        "eligible_events": 0, "planned_windows": 0, "omitted_windows": 0,
        "failed_windows": 0, "warnings": [],
    }}
    details = result["highlight_generation"]
    directory_ready = False
    try:
        config = HighlightConfig(**config) if isinstance(config, dict) else (config or HighlightConfig())
        config.validate()
        details.update(config=config.public_settings(), source=config.source)
        if not config.enabled:
            details["status"] = "disabled"
            return result
        prepare_directory(run_directory)
        directory_ready = True
        details["directory"] = "highlights"
        if not select_events(events, config):
            details["status"] = "no_eligible_events"
        else:
            source = input_video_path if config.source == "original" else annotated_video_path
            if source is None:
                raise ValueError("Explicit highlight source is required")
            info = probe_source(source, video_metadata if config.source == "original" else None)
            details.update({key: info[key] for key in ("fps", "duration_seconds", "duration_source")})
            plan = plan_highlights(events, info["duration_seconds"], config)
            details.update(eligible_events=plan["eligible_events"],
                           planned_windows=len(plan["windows"]), omitted_windows=plan["omitted_windows"])
            for window in plan["windows"]:
                try:
                    clip = export_clip(source, run_directory, uuid4().hex, window, info, config)
                    result["highlights"].append({**window, **clip, "source": config.source})
                except Exception:
                    logger.exception("Optional highlight clip export failed")
                    details["failed_windows"] += 1
            if details["failed_windows"]:
                details["warnings"].append("Some highlight exports failed; see the local analysis log.")
                details["status"] = "partial" if result["highlights"] else "failed"
            else:
                details["status"] = "completed" if result["highlights"] else "no_eligible_events"
    except Exception:
        logger.exception("Optional highlight generation failed; preserving main analysis")
        details["status"] = "failed"
        details["warnings"].append("Highlight generation unavailable; see the local analysis log.")

    if directory_ready:
        temporary = None
        temporary_owned = False
        try:
            details["manifest_path"] = "highlights/highlights.json"
            temporary = confined_path(run_directory, f"highlights/.manifest_{uuid4().hex}.tmp")
            with temporary.open("x", encoding="utf-8") as stream:
                temporary_owned = True
                json.dump(result, stream, indent=2, allow_nan=False)
            temporary.replace(confined_path(run_directory, details["manifest_path"]))
        except Exception:
            logger.exception("Could not save highlight manifest")
            details["manifest_path"] = None
            details["warnings"].append("Highlight manifest could not be saved.")
            details["status"] = "partial" if result["highlights"] else "failed"
        finally:
            if temporary_owned:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not clean temporary highlight manifest", exc_info=True)
    return result

