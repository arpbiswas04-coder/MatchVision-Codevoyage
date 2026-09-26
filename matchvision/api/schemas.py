"""Public job schemas contain no local paths or exception tracebacks."""
from typing import Literal
from pydantic import BaseModel, Field


class JobStatus(BaseModel):
    analysis_id: str
    status: Literal["uploaded", "queued", "processing", "completed", "failed"]
    progress: int = Field(ge=0, le=100)
    stage: str
    error: str | None = None
    filename: str
    created_at: str


class UploadResponse(JobStatus):
    status_url: str
    results_url: str
