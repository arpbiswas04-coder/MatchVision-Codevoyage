"""Optional event-driven highlights, independent of model inference."""
from .planning import HighlightConfig, plan_highlights
from .service import generate_highlights
from .paths import resolve_highlight_asset

__all__ = ["HighlightConfig", "plan_highlights", "generate_highlights", "resolve_highlight_asset"]
