"""One-worker in-memory MVP queue. Restarting the server loses job registrations."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import logging
from threading import RLock
from uuid import uuid4

from matchvision.json_io import write_json
from .storage import analysis_directory, safe_file, validate_id

logger = logging.getLogger(__name__)


class QueueFull(Exception):
    pass


class JobManager:
    def __init__(self, settings):
        self.settings = settings
        self._lock = RLock()
        self._jobs = {}
        self._accepting = True
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="matchvision")

    def register(self, filename):
        with self._lock:
            active = sum(job["status"] in ("uploaded", "queued", "processing") for job in self._jobs.values())
            if not self._accepting or active >= self.settings.max_active_jobs:
                raise QueueFull()
            analysis_id = uuid4().hex
            self._jobs[analysis_id] = {
                "analysis_id": analysis_id, "status": "uploaded", "progress": 0,
                "stage": "Video uploaded", "error": None, "filename": filename,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            return analysis_id

    def discard(self, analysis_id):
        with self._lock:
            self._jobs.pop(analysis_id, None)

    def get(self, analysis_id):
        validate_id(analysis_id)
        with self._lock:
            if analysis_id not in self._jobs:
                raise KeyError(analysis_id)
            return dict(self._jobs[analysis_id])

    def _update(self, analysis_id, **values):
        with self._lock:
            self._jobs[analysis_id].update(values)

    def submit(self, analysis_id, source, shot_calibration=None):
        with self._lock:
            if not self._accepting:
                raise QueueFull()
            self._update(analysis_id, status="queued", stage="Queued for analysis")
            self._executor.submit(self._run, analysis_id, source, shot_calibration)

    def _run(self, analysis_id, source, shot_calibration):
        self._update(analysis_id, status="processing", stage="Preparing video", progress=1)
        try:
            # Heavy imports and model loading happen only in the worker.
            from matchvision import analyze_match
            from .media import convert_browser_video, public_results
            from .summary import build_summary

            def progress(percent, stage):
                # Reserve the last 5% for real API media/finalisation work.
                current = self.get(analysis_id)["progress"]
                self._update(analysis_id, progress=max(current, min(95, int(percent * 0.95))), stage=stage)

            result = analyze_match(source, self.settings.output_root, analysis_id=analysis_id,
                                   progress_callback=progress, shot_calibration=shot_calibration)
            directory = analysis_directory(self.settings.output_root, analysis_id)
            self._update(analysis_id, progress=96, stage="Preparing browser video")
            destination = safe_file(directory, "api_results.json")

            def save_public(conversion):
                projected = public_results(result, analysis_id, directory, conversion)
                write_json(destination, projected)
                try:
                    summary_path = safe_file(directory, "api_summary.json.tmp")
                    summary_path.write_text(json.dumps(build_summary(projected), allow_nan=False), encoding="utf-8")
                    summary_path.replace(safe_file(directory, "api_summary.json"))
                except Exception:
                    logger.exception("Could not cache dashboard summary for %s; full results preserved", analysis_id)

            # Keep a usable public result even if optional conversion exhausts disk space.
            save_public({"status": "not_generated", "reason": "Browser conversion has not been recorded"})
            try:
                conversion = convert_browser_video(directory, self.settings.conversion_timeout_seconds)
            except Exception:
                logger.exception("Optional browser conversion failed for %s", analysis_id)
                conversion = {"status": "failed", "reason": "Browser conversion unavailable; see the server log"}
            self._update(analysis_id, progress=99, stage="Finalising API results")
            try:
                save_public(conversion)
            except Exception:
                logger.exception("Could not persist optional browser metadata; preserving public analysis %s", analysis_id)
            self._update(analysis_id, status="completed", progress=100, stage="Completed")
            logger.info("API analysis %s completed", analysis_id)
        except Exception:
            logger.exception("API analysis %s failed", analysis_id)
            stage = self.get(analysis_id)["stage"]
            self._update(analysis_id, status="failed",
                         error=f"Analysis failed during {stage}. See the server log using this analysis ID.")

    def shutdown(self):
        with self._lock:
            self._accepting = False
        self._executor.shutdown(wait=True, cancel_futures=True)





