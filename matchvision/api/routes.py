"""HTTP adapters: uploads and job queries, never model inference in a request."""
import json
import logging
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from .jobs import QueueFull
from .media import media_file
from .schemas import JobStatus, UploadResponse
from .storage import analysis_directory, clean_filename, inspect_upload, safe_file

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


def lookup(request, analysis_id):
    try:
        return request.app.state.jobs.get(analysis_id)
    except (ValueError, KeyError):
        raise HTTPException(404, "Unknown analysis ID") from None


def completed_directory(request, analysis_id):
    job = lookup(request, analysis_id)
    if job["status"] != "completed":
        raise HTTPException(409, {"message": "Analysis is not complete", **job})
    try:
        return analysis_directory(request.app.state.settings.output_root, analysis_id)
    except (ValueError, OSError):
        raise HTTPException(404, "Analysis output is unavailable") from None


@router.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "service": "MatchVision API"}


@router.post("/matches/upload", status_code=202, response_model=UploadResponse, tags=["Matches"])
async def upload_match(
    request: Request,
    file: Annotated[UploadFile, File(description="Your football video: MP4, AVI, MOV or MKV")],
    shot_calibration: Annotated[str | None, Form(
        description="Optional input-specific calibration JSON text. Leave blank unless validated for this video.")] = None,
):
    settings, jobs = request.app.state.settings, request.app.state.jobs
    analysis_id = None
    directory = source = None
    created = submitted = False
    try:
        try:
            filename, extension = clean_filename(file.filename)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        calibration = None
        if shot_calibration and shot_calibration.strip():
            if len(shot_calibration) > 65536:
                raise HTTPException(400, "Calibration JSON must be at most 65536 characters")
            try:
                calibration = json.loads(shot_calibration)
                if not isinstance(calibration, dict):
                    raise ValueError()
                json.dumps(calibration, allow_nan=False)
            except (ValueError, TypeError, RecursionError):
                raise HTTPException(400, "Calibration must be a finite JSON object") from None
        if file.size is not None and file.size > settings.max_upload_bytes:
            raise HTTPException(413, "Video exceeds the configured upload size limit")
        try:
            analysis_id = jobs.register(filename)
        except QueueFull:
            raise HTTPException(503, "Analysis queue is full; retry later", headers={"Retry-After": "30"}) from None
        directory = analysis_directory(settings.upload_root, analysis_id)
        directory.mkdir(parents=True, exist_ok=False)
        created = True
        source = safe_file(directory, "original" + extension)
        total = 0
        with source.open("xb") as stream:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise HTTPException(413, "Video exceeds the configured upload size limit")
                await run_in_threadpool(stream.write, chunk)
        if total == 0:
            raise HTTPException(400, "The uploaded video is empty")
        try:
            await run_in_threadpool(inspect_upload, source)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        jobs.submit(analysis_id, source, calibration)
        submitted = True
        logger.info("Accepted upload %s (%d bytes)", analysis_id, total)
        return {**jobs.get(analysis_id),
                "status_url": f"/api/matches/{analysis_id}/status",
                "results_url": f"/api/matches/{analysis_id}/results"}
    except HTTPException:
        raise
    except QueueFull:
        raise HTTPException(503, "Server is shutting down; retry later") from None
    except Exception:
        logger.exception("Upload could not be stored or inspected (analysis %s)", analysis_id)
        raise HTTPException(500, "Could not store or inspect the upload; see the server log") from None
    finally:
        try:
            await file.close()
        except Exception:
            logger.warning("Could not close multipart upload", exc_info=True)
        if analysis_id and not submitted:
            jobs.discard(analysis_id)
            if created:
                try:
                    # Only this request's owned file and now-empty directory; no recursive delete.
                    if source is not None:
                        source.unlink(missing_ok=True)
                    directory.rmdir()
                except OSError:
                    logger.warning("Could not clean rejected upload %s", analysis_id, exc_info=True)


@router.get("/matches/{analysis_id}/status", response_model=JobStatus, tags=["Matches"])
def match_status(request: Request, analysis_id: str):
    return lookup(request, analysis_id)


@router.get("/matches/{analysis_id}/results", tags=["Matches"])
def match_results(request: Request, analysis_id: str):
    directory = completed_directory(request, analysis_id)
    try:
        path = safe_file(directory, "api_results.json")
        if not path.is_file():
            raise FileNotFoundError()
        # Only the sanitized projection is served, never the engine's local analysis.json.
        return FileResponse(path, media_type="application/json")
    except (OSError, ValueError):
        raise HTTPException(404, "Public analysis results are unavailable") from None


@router.get("/matches/{analysis_id}/summary", tags=["Matches"])
def match_summary(request: Request, analysis_id: str):
    directory = completed_directory(request, analysis_id)
    try:
        path = safe_file(directory, "api_summary.json")
        if path.is_file():
            return FileResponse(path, media_type="application/json")
        # Compatibility fallback for a completed run without a cached summary.
        from .summary import build_summary
        public = json.loads(safe_file(directory, "api_results.json").read_text(encoding="utf-8"))
        return build_summary(public)
    except (OSError, ValueError):
        raise HTTPException(404, "Dashboard summary is unavailable") from None


@router.get("/matches/{analysis_id}/video", tags=["Media"])
def annotated_video(request: Request, analysis_id: str, download: bool = False):
    directory = completed_directory(request, analysis_id)
    try:
        if download:
            try:
                path = media_file(directory, "video", "output_video.avi")
                return FileResponse(path, media_type="video/x-msvideo", filename=path.name)
            except FileNotFoundError:
                pass
        path = media_file(directory, "video", "output_video.mp4")
        return FileResponse(path, media_type="video/mp4",
                            filename=path.name if download else None)
    except FileNotFoundError:
        try:
            media_file(directory, "video", "output_video.avi")
        except (ValueError, OSError):
            raise HTTPException(404, "Annotated video is unavailable") from None
        raise HTTPException(409, {"message": "Browser MP4 is unavailable; download the original AVI",
                                 "download_url": f"/api/matches/{analysis_id}/video?download=true"}) from None
    except (ValueError, OSError):
        raise HTTPException(404, "Annotated video is unavailable") from None


@router.get("/matches/{analysis_id}/heatmaps/{name}", tags=["Media"])
def heatmap(request: Request, analysis_id: str, name: str):
    directory = completed_directory(request, analysis_id)
    try:
        return FileResponse(media_file(directory, "heatmaps", name), media_type="image/png")
    except (ValueError, OSError):
        raise HTTPException(404, "Heatmap is unavailable") from None


@router.get("/matches/{analysis_id}/highlights/{name}", tags=["Media"])
def highlight(request: Request, analysis_id: str, name: str):
    directory = completed_directory(request, analysis_id)
    try:
        path = media_file(directory, "highlights", name)
        return FileResponse(path, media_type="video/mp4" if path.suffix == ".mp4" else "video/x-msvideo",
                            filename=path.name if path.suffix == ".avi" else None)
    except (ValueError, OSError):
        raise HTTPException(404, "Highlight is unavailable") from None


