"""Conservative pass inference from observed player possession, never team carry-forward."""
from dataclasses import asdict, dataclass
import logging
import math
from numbers import Integral, Real

from .events import PassEvent

logger = logging.getLogger(__name__)


def _positive_seconds(value, name):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")


@dataclass(frozen=True)
class PassDetectionConfig:
    stable_possession_seconds: float = 0.24
    max_evidence_gap_seconds: float = 0.12
    max_transition_seconds: float = 2.0
    max_unobserved_seconds: float = 0.40
    minimum_support_ratio: float = 0.60

    def __post_init__(self):
        for name in ("stable_possession_seconds", "max_evidence_gap_seconds",
                     "max_transition_seconds", "max_unobserved_seconds"):
            _positive_seconds(getattr(self, name), name)
        if self.max_transition_seconds < self.stable_possession_seconds:
            raise ValueError("Transition window must allow receiver stability confirmation")
        ratio = self.minimum_support_ratio
        if isinstance(ratio, bool) or not isinstance(ratio, Real) or not math.isfinite(ratio) or not 0 < ratio <= 1:
            raise ValueError("minimum_support_ratio must be in (0, 1]")

    def frame_thresholds(self, fps):
        _positive_seconds(fps, "fps")
        return {
            # Two independent sightings are the minimum evidence, even at very low FPS.
            "stable_observations": max(2, math.ceil(self.stable_possession_seconds * fps)),
            "max_evidence_gap_frames": math.floor(self.max_evidence_gap_seconds * fps),
            "max_transition_frames": math.floor(self.max_transition_seconds * fps),
            "max_unobserved_frames": math.floor(self.max_unobserved_seconds * fps),
        }


def _player_id(value):
    # JSON track keys are strings; live ByteTrack keys are integer/NumPy integer.
    if isinstance(value, str):
        return int(value) if value.isdigit() else None
    if isinstance(value, Integral) and not isinstance(value, bool) and value >= 0:
        return int(value)
    return None


def _position(track):
    value = track.get("position_transformed")
    try:
        if len(value) != 2 or any(isinstance(v, bool) or not isinstance(v, Real) for v in value):
            return None
        point = tuple(float(v) for v in value)
    except (TypeError, ValueError, OverflowError):
        return None
    return point if all(math.isfinite(v) for v in point) else None


def _track(frame, player_id):
    return frame.get(player_id, frame.get(str(player_id)))


def _owner(players, ball_frame, conflicting_ids):
    """Return (status, owner). Missing data is not evidence of a free ball."""
    balls = list(ball_frame.values())
    if len(balls) != 1 or not balls[0].get("is_observed", False):
        return "unobserved", None
    if not players or not any(p.get("possession_evaluated", False) for p in players.values()):
        return "unobserved", None
    holders = [(key, p) for key, p in players.items() if p.get("has_ball", False)]
    if len(holders) > 1:
        return "ambiguous", None
    if not holders:
        return "unassigned", None
    raw_id, player = holders[0]
    player_id = _player_id(raw_id)
    team = player.get("team")
    if (player_id is None or player_id in conflicting_ids or team not in (1, 2)
            or isinstance(team, bool) or not player.get("possession_evaluated", False)):
        return "ambiguous", None
    return "owned", (player_id, int(team), _position(player))


@dataclass
class _PossessionRun:
    player_id: int
    team: int
    first_frame: int
    last_frame: int
    first_position: tuple | None
    last_position: tuple | None
    support: int = 1

    @property
    def key(self):
        return self.player_id, self.team

    @property
    def support_ratio(self):
        return self.support / (self.last_frame - self.first_frame + 1)


def _pass_event(source, receiver, confirmation_frame, player_frames, fps, config):
    # Require co-visible, consistently labelled identities at reception. A disappearing
    # track replaced by a new ID alone cannot establish a pass between two people.
    reception = player_frames[receiver.first_frame]
    passer = _track(reception, source.player_id)
    recipient = _track(reception, receiver.player_id)
    if (passer is None or recipient is None or passer.get("team") != source.team
            or recipient.get("team") != source.team):
        return None
    from_position, to_position = source.last_position, receiver.first_position
    distance = math.dist(from_position, to_position) if from_position is not None and to_position is not None else None
    if distance is not None and not math.isfinite(distance):
        distance = None
    elapsed = (confirmation_frame - source.last_frame) / fps
    confidence = round(min(0.95, 0.55 + 0.20 * min(source.support_ratio, receiver.support_ratio)
                           + 0.10 * max(0.0, 1.0 - elapsed / config.max_transition_seconds)
                           + (0.10 if distance is not None else 0.0)), 3)
    return PassEvent.at_frame(
        "pass", receiver.first_frame, fps, team=source.team,
        player_from=source.player_id, player_to=receiver.player_id,
        from_position=from_position, to_position=to_position, distance=distance,
        confidence=confidence, release_frame=source.last_frame,
        confirmation_frame=confirmation_frame,
    ).to_dict()


def detect_passes(tracks, fps, config=None):
    """Return pass events and diagnostics without changing the input tracks.

    A receiver run needs stable observed evidence, allowing only short missing
    evidence gaps. Brief competing assignments reset the candidate, not the
    confirmed holder. A confirmed opponent becomes the new holder without a pass.
    The receiver must be confirmed inside the transition window measured from
    the source's final observed possession. No end-of-clip candidate is forced
    into an event. Timestamps refer to the receiver's first supported frame;
    confirmation_frame records when sufficient evidence became available.
    """
    config = config or PassDetectionConfig()
    limits = config.frame_thresholds(fps)
    player_frames = tracks.get("players", [])
    ball_frames = tracks.get("ball", [])
    labels = {}
    for frame in player_frames:
        for key, player in frame.items():
            player_id, team = _player_id(key), player.get("team")
            if player_id is not None and team in (1, 2) and not isinstance(team, bool):
                labels.setdefault(player_id, set()).add(int(team))
    conflicting_ids = {key for key, teams in labels.items() if len(teams) > 1}
    candidate = active = None
    missing_run = 0
    events, stable_players = [], {}
    coverage = {"owned": 0, "unassigned": 0, "unobserved": 0, "ambiguous": 0}
    rejected_identity_transitions = 0
    for frame_index, players in enumerate(player_frames):
        ball = ball_frames[frame_index] if frame_index < len(ball_frames) else {}
        status, observation = _owner(players, ball, conflicting_ids)
        coverage[status] += 1
        missing_run = missing_run + 1 if status == "unobserved" else 0
        if status == "ambiguous" or missing_run > limits["max_unobserved_frames"]:
            candidate = active = None
        if active is not None and frame_index - active.last_frame > limits["max_transition_frames"]:
            active = None
        if observation is None:
            if candidate is not None and frame_index - candidate.last_frame > limits["max_evidence_gap_frames"]:
                candidate = None
            continue

        player_id, team, position = observation
        key = player_id, team
        if (candidate is None or candidate.key != key
                or frame_index - candidate.last_frame - 1 > limits["max_evidence_gap_frames"]):
            candidate = _PossessionRun(player_id, team, frame_index, frame_index, position, position)
        else:
            candidate.last_frame = frame_index
            candidate.last_position = position
            candidate.support += 1

        # Returning to the confirmed owner cancels a noisy handoff. Only observed
        # evidence refreshes the source's release position/time, never carry-forward.
        if active is not None and active.key == key and active is not candidate:
            active.last_frame = frame_index
            active.last_position = position
            active.support += 1

        if (candidate.support < limits["stable_observations"]
                or candidate.support_ratio < config.minimum_support_ratio):
            continue
        stable_players[str(player_id)] = team
        if active is not None and active.key != key:
            if (active.team == team and active.player_id != player_id
                    and active.support_ratio >= config.minimum_support_ratio
                    and candidate.first_frame > active.last_frame
                    and frame_index - active.last_frame <= limits["max_transition_frames"]):
                event = _pass_event(active, candidate, frame_index, player_frames, fps, config)
                if event is not None:
                    events.append(event)
                else:
                    rejected_identity_transitions += 1
        active = candidate

    metadata = {
        "status": "completed" if stable_players else "insufficient_data",
        "detectors": ["pass"], "method": "debounced_observed_player_possession",
        "config_seconds": asdict(config), "frame_thresholds": limits, "fps": float(fps),
        "frame_coverage": coverage, "stable_players": stable_players,
        "conflicting_team_track_ids": sorted(conflicting_ids),
        "rejected_identity_transitions": rejected_identity_transitions,
        "detected_passes": len(events),
        "timestamp_semantics": "first_supported_receiver_frame_confirmed_later",
        "position_semantics": "passer_at_last_possession_receiver_at_first_receipt_in_pitch_meters",
        "identity_policy": "both_tracks_visible_and_same_team_at_reception",
        "confidence_method": "heuristic_support_and_timing_score_not_calibrated_probability",
        "confidence_formula": "min(0.95, 0.55 + 0.20*min_support_ratio + 0.10*(1-confirmation_delay/window) + 0.10*distance_available)",
        "limitations": [
            "Detected successful handoffs only; not attempted passes or pass accuracy.",
            "Possession errors, occlusion and tracking ID switches can cause missed or incorrect events.",
            "Distance is endpoint separation under the existing pitch calibration, not ball travel length.",
        ],
    }
    logger.info("Pass detection: %d events, %d stable player IDs, status=%s",
                len(events), len(stable_players), metadata["status"])
    return {"events": events, "event_detection": metadata}


def add_pass_statistics(players, teams, detection):
    """Add detected-event counts; unavailable identity evidence is represented by null."""
    events = detection["events"]
    stable_players = detection["event_detection"]["stable_players"]
    for player in players:
        player_id = player["player_id"]
        available = str(player_id) in stable_players
        player["pass_statistics_available"] = available
        player["successful_passes"] = sum(e["player_from"] == player_id for e in events) if available else None
        player["passes_received"] = sum(e["player_to"] == player_id for e in events) if available else None
    for team in teams:
        available = team["team_id"] in stable_players.values()
        team["pass_statistics_available"] = available
        team["total_detected_successful_passes"] = sum(e["team"] == team["team_id"] for e in events) if available else None

