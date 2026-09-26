"""Pure event selection and highlight-window planning; no video or filesystem I/O."""
from dataclasses import dataclass
import math
from numbers import Integral, Real

IMPORTANT_EVENT_TYPES = frozenset({"shot", "goal", "save"})


@dataclass(frozen=True)
class HighlightConfig:
    enabled: bool = True
    before_seconds: float = 5.0
    after_seconds: float = 6.0
    merge_gap_seconds: float = 1.0
    minimum_confidence: float = 0.85
    event_types: tuple = ("shot",)
    max_clips: int = 20
    source: str = "original"
    backend: str = "auto"
    export_timeout_seconds: float = 600.0

    def validate(self):
        # Validation happens within the optional generation stage, so invalid
        # highlight settings cannot abort the main analysis before it starts.
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be boolean")
        for name in ("before_seconds", "after_seconds", "merge_gap_seconds"):
            value = getattr(self, name)
            if not finite_number(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.before_seconds + self.after_seconds <= 0:
            raise ValueError("Highlight duration must be positive")
        if not finite_number(self.minimum_confidence) or not 0 <= self.minimum_confidence <= 1:
            raise ValueError("minimum_confidence must be in [0, 1]")
        if (not isinstance(self.event_types, (tuple, list)) or not self.event_types
                or any(not isinstance(kind, str) or kind not in IMPORTANT_EVENT_TYPES for kind in self.event_types)):
            raise ValueError("Only shot, goal and save events are eligible; ordinary passes are excluded")
        if isinstance(self.max_clips, bool) or not isinstance(self.max_clips, Integral) or self.max_clips < 1:
            raise ValueError("max_clips must be a positive integer")
        if self.source not in ("original", "annotated") or self.backend not in ("auto", "ffmpeg", "opencv"):
            raise ValueError("Invalid highlight source or backend")
        if not finite_number(self.export_timeout_seconds) or self.export_timeout_seconds <= 0:
            raise ValueError("Export timeout must be positive and finite")

    def public_settings(self):
        return {"enabled": self.enabled, "before_seconds": float(self.before_seconds),
                "after_seconds": float(self.after_seconds), "merge_gap_seconds": float(self.merge_gap_seconds),
                "minimum_confidence": float(self.minimum_confidence), "event_types": list(self.event_types),
                "max_clips": int(self.max_clips), "source": self.source, "backend": self.backend,
                "export_timeout_seconds": float(self.export_timeout_seconds)}


def finite_number(value):
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def select_events(events, config):
    config.validate()
    selected, seen = [], set()
    for event in events:
        if not isinstance(event, dict) or event.get("type") not in config.event_types:
            continue
        timestamp, confidence = event.get("timestamp"), event.get("confidence")
        if (not finite_number(timestamp) or timestamp < 0 or not finite_number(confidence)
                or not config.minimum_confidence <= confidence <= 1):
            continue
        item = {"event_type": event["type"], "timestamp": float(timestamp), "confidence": float(confidence)}
        for field in ("team", "player"):
            value = event.get(field)
            if isinstance(value, Integral) and not isinstance(value, bool) and value >= 0:
                item[field] = int(value)
        identity = (item["event_type"], item["timestamp"], item.get("team"), item.get("player"))
        if identity not in seen:
            selected.append(item)
            seen.add(identity)
    return sorted(selected, key=lambda event: (event["timestamp"], event["event_type"]))


def plan_highlights(events, duration_seconds, config=None):
    config = config or HighlightConfig()
    config.validate()
    if not finite_number(duration_seconds) or duration_seconds <= 0:
        raise ValueError("Source duration must be positive and finite")
    selected = select_events(events, config)
    windows = []
    for event in selected:
        # An event at or beyond end-of-stream has no corresponding video frame.
        if event["timestamp"] >= duration_seconds:
            continue
        start = max(0.0, event["timestamp"] - config.before_seconds)
        end = min(float(duration_seconds), event["timestamp"] + config.after_seconds)
        if end <= start:
            continue
        if windows and start <= windows[-1]["end"] + config.merge_gap_seconds:
            windows[-1]["end"] = max(windows[-1]["end"], end)
            windows[-1]["events"].append(event)
        else:
            windows.append({"start": start, "end": end, "events": [event]})
    for window in windows:
        primary = max(window["events"], key=lambda event: (event["confidence"], -event["timestamp"]))
        window.update(event_type=primary["event_type"], timestamp=primary["timestamp"],
                      confidence=primary["confidence"],
                      event_types=sorted({event["event_type"] for event in window["events"]}))
    omitted = max(0, len(windows) - config.max_clips)
    # Retain strongest actions when limiting output, then restore chronological order.
    kept = sorted(windows, key=lambda window: (-window["confidence"], window["start"]))[:config.max_clips]
    return {"windows": sorted(kept, key=lambda window: window["start"]),
            "eligible_events": sum(len(window["events"]) for window in windows),
            "merged_window_count": len(windows), "omitted_windows": omitted}

