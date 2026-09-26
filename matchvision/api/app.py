"""Run manually: python -m uvicorn matchvision.api.app:app --host 127.0.0.1 --port 8000"""
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .jobs import JobManager
from .middleware import UploadLimitMiddleware
from .routes import router

logger = logging.getLogger(__name__)


def create_app(settings=None):
    settings = settings or Settings.from_environment()

    @asynccontextmanager
    async def lifespan(application):
        logging.getLogger("matchvision").setLevel(logging.INFO)
        # Uvicorn owns its handlers; add an application handler for engine progress/logs.
        application_logger = logging.getLogger("matchvision")
        if not application_logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
            application_logger.addHandler(handler)
            application_logger.propagate = False
        settings.upload_root.mkdir(parents=True, exist_ok=True)
        settings.output_root.mkdir(parents=True, exist_ok=True)
        application.state.settings = settings
        application.state.jobs = JobManager(settings)
        try:
            yield
        finally:
            # Running inference is allowed to finish; queued work is cancelled.
            await run_in_threadpool(application.state.jobs.shutdown)

    application = FastAPI(title="MatchVision API", version="0.1.0", lifespan=lifespan,
                          description="Upload your own match video and poll its background analysis.")
    application.add_middleware(UploadLimitMiddleware, max_bytes=settings.max_upload_bytes + 1024 * 1024)
    application.add_middleware(
        CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type", "Range"],
        expose_headers=["Content-Length", "Content-Range", "Accept-Ranges", "Retry-After"])
    application.include_router(router)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Omit raw request input and exception context (which may include private paths).
        return JSONResponse(status_code=422, content={"detail": [
            {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
            for error in exc.errors()]})

    @application.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error("Unhandled API error", exc_info=(type(exc), exc, exc.__traceback__))
        return JSONResponse(status_code=500, content={"detail": "Internal server error; see the server log"})

    return application


app = create_app()
