"""Validated common event records and optional pitch measurements for inferred passes."""
from dataclasses import dataclass
import math
from numbers import Integral, Real


def _nonnegative_integer(value, name):
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


@dataclass(frozen=True)
class MatchEvent:
    type: str
    timestamp: float
    frame: int
    team: int | None = None
    player_from: int | None = None
    player_to: int | None = None
    confidence: float | None = None

    def __post_init__(self):
        if not isinstance(self.type, str) or not self.type.strip():
            raise ValueError("Event type must be a nonempty string")
        _nonnegative_integer(self.frame, "frame")
        if (isinstance(self.timestamp, bool) or not isinstance(self.timestamp, Real)
                or not math.isfinite(self.timestamp) or self.timestamp < 0):
            raise ValueError("Timestamp must be nonnegative and finite")
        if self.team is not None:
            _nonnegative_integer(self.team, "team")
            if self.team not in (1, 2):
                raise ValueError("Team must be 1, 2 or None")
        for name in ("player_from", "player_to"):
            if getattr(self, name) is not None:
                _nonnegative_integer(getattr(self, name), name)
        if self.confidence is not None:
            if (isinstance(self.confidence, bool) or not isinstance(self.confidence, Real)
                    or not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1):
                raise ValueError("Confidence must be between 0 and 1 or None")

    @classmethod
    def at_frame(cls, event_type, frame, fps, **details):
        _nonnegative_integer(frame, "frame")
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError("FPS must be positive and finite")
        return cls(type=event_type, timestamp=frame / fps, frame=frame, **details)

    def to_dict(self):
        return {
            "type": self.type, "timestamp": float(self.timestamp), "frame": int(self.frame),
            "team": int(self.team) if self.team is not None else None,
            "player_from": int(self.player_from) if self.player_from is not None else None,
            "player_to": int(self.player_to) if self.player_to is not None else None,
            "confidence": float(self.confidence) if self.confidence is not None else None,
        }


@dataclass(frozen=True)
class PassEvent(MatchEvent):
    """Successful-pass hypothesis, with optional pitch-space endpoint measurements."""
    from_position: tuple | None = None
    to_position: tuple | None = None
    distance: float | None = None
    release_frame: int | None = None
    confirmation_frame: int | None = None

    def __post_init__(self):
        super().__post_init__()
        if (self.type != "pass" or self.team is None or self.player_from is None
                or self.player_to is None or self.player_from == self.player_to):
            raise ValueError("Pass events require a team and two distinct players")
        for name in ("from_position", "to_position"):
            point = getattr(self, name)
            if point is None:
                continue
            try:
                valid = len(point) == 2 and all(
                    isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)
                    for value in point
                )
            except TypeError:
                valid = False
            if not valid:
                raise ValueError(f"{name} must contain two finite pitch coordinates or None")
            object.__setattr__(self, name, tuple(float(value) for value in point))
        if self.distance is not None:
            if (isinstance(self.distance, bool) or not isinstance(self.distance, Real)
                    or not math.isfinite(self.distance) or self.distance < 0
                    or self.from_position is None or self.to_position is None):
                raise ValueError("Pass distance requires both positions and a finite nonnegative value")
        if self.release_frame is not None:
            _nonnegative_integer(self.release_frame, "release_frame")
            if self.release_frame >= self.frame:
                raise ValueError("Release evidence must precede reception")
        if self.confirmation_frame is not None:
            _nonnegative_integer(self.confirmation_frame, "confirmation_frame")
            if self.confirmation_frame < self.frame:
                raise ValueError("Confirmation cannot precede reception")

    def to_dict(self):
        return {
            **super().to_dict(),
            "from_position": list(self.from_position) if self.from_position is not None else None,
            "to_position": list(self.to_position) if self.to_position is not None else None,
            "distance": float(self.distance) if self.distance is not None else None,
            "release_frame": int(self.release_frame) if self.release_frame is not None else None,
            "confirmation_frame": int(self.confirmation_frame) if self.confirmation_frame is not None else None,
        }



@dataclass(frozen=True)
class ShotEvent(MatchEvent):
    """A probable shot hypothesis, never a guarantee of intent, target or outcome."""
    player: int | None = None
    position: tuple | None = None
    confirmation_frame: int | None = None

    def __post_init__(self):
        super().__post_init__()
        if self.type != "shot" or self.team is None or self.player is None or self.confidence is None:
            raise ValueError("Shot hypotheses require type, team, player and confidence")
        _nonnegative_integer(self.player, "player")
        try:
            valid = len(self.position) == 2 and all(
                isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)
                for value in self.position
            )
        except TypeError:
            valid = False
        if not valid:
            raise ValueError("Shot position must contain two finite pitch coordinates")
        object.__setattr__(self, "position", tuple(float(value) for value in self.position))
        if self.confirmation_frame is not None:
            _nonnegative_integer(self.confirmation_frame, "confirmation_frame")
            if self.confirmation_frame < self.frame:
                raise ValueError("Shot confirmation cannot precede approximate release")

    def to_dict(self):
        return {
            **super().to_dict(), "player": int(self.player), "position": list(self.position),
            "classification": "probable_shot",
            "confirmation_frame": int(self.confirmation_frame) if self.confirmation_frame is not None else None,
        }


def merge_event_detections(passes, shots, other_events=()):
    """Replace prior estimates and keep one time-ordered common events timeline."""
    retained = [event for event in other_events if event.get("type") not in ("pass", "shot")]
    events = sorted(retained + passes["events"] + shots["events"],
                    key=lambda event: (event["frame"], event["type"]))
    return {
        "events": events,
        # Preserve legacy pass status/diagnostics; shot status is explicitly separate.
        "event_detection": {**passes["event_detection"], "detectors": ["pass", "shot"],
                            "shots": shots["event_detection"], "timeline_event_count": len(events)},
        "shot_calibration": shots["calibration"],
    }
