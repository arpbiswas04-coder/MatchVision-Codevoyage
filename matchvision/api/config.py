"""Local deployment settings; all storage roots are chosen by the operator."""
from dataclasses import dataclass
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    upload_root: Path
    output_root: Path
    max_upload_bytes: int = 2 * 1024 * 1024 * 1024
    max_active_jobs: int = 8
    conversion_timeout_seconds: int = 1800
    cors_origins: tuple = ("http://localhost:5173", "http://127.0.0.1:5173")

    @classmethod
    def from_environment(cls):
        settings = cls(
            upload_root=Path(os.getenv("MATCHVISION_UPLOAD_ROOT", str(PROJECT_ROOT / "uploads"))).resolve(),
            output_root=Path(os.getenv("MATCHVISION_OUTPUT_ROOT", str(PROJECT_ROOT / "outputs"))).resolve(),
            max_upload_bytes=int(os.getenv("MATCHVISION_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024))),
            max_active_jobs=int(os.getenv("MATCHVISION_MAX_ACTIVE_JOBS", "8")),
            conversion_timeout_seconds=int(os.getenv("MATCHVISION_CONVERSION_TIMEOUT_SECONDS", "1800")),
            cors_origins=tuple(origin.strip() for origin in os.getenv(
                "MATCHVISION_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173").split(",") if origin.strip()),
        )
        if min(settings.max_upload_bytes, settings.max_active_jobs, settings.conversion_timeout_seconds) <= 0:
            raise ValueError("Upload, queue and timeout limits must be positive")
        if "*" in settings.cors_origins:
            raise ValueError("Configure explicit CORS origins")
        return settings

