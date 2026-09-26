"""Generated artifact paths stay beneath a trusted analysis directory."""
from pathlib import Path
import re

ASSET_PATTERN = re.compile(r"highlights/clip_[0-9a-f]{32}\.(?:mp4|avi)")


def confined_path(run_directory, relative_path):
    root = Path(run_directory).resolve()
    relative = Path(relative_path)
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        raise ValueError("Artifact path must be relative and confined")
    target = (root / relative).resolve()
    target.relative_to(root)  # Also rejects existing symlinks/junctions escaping the root.
    if target == root:
        raise ValueError("An artifact cannot be the analysis root")
    return target


def prepare_directory(run_directory):
    directory = confined_path(run_directory, "highlights")
    directory.mkdir(parents=True, exist_ok=True)
    return confined_path(run_directory, "highlights")


def resolve_highlight_asset(run_directory, asset_path):
    """Resolve only a generated clip reference, never a client-supplied arbitrary path.

    The caller must resolve the trusted analysis directory from its own analysis
    registry, not accept that root from an HTTP request. No serving endpoint is added.
    """
    if not isinstance(asset_path, str) or not ASSET_PATTERN.fullmatch(asset_path):
        raise ValueError("Invalid highlight asset reference")
    path = confined_path(run_directory, asset_path)
    if not path.is_file():
        raise FileNotFoundError("Highlight asset is unavailable")
    return path
