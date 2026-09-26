"""Conservative probable-shot inference; never infer goal locations from pitch bounds."""
from collections import Counter
from dataclasses import asdict, dataclass
import logging
import math
from numbers import Integral, Real

from .events import ShotEvent

logger = logging.getLogger(__name__)


def _number(value):
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def _id(value):
    if isinstance(value, str):
        return int(value) if value.isdecimal() else None
    return int(value) if isinstance(value, Integral) and not isinstance(value, bool) and value >= 0 else None


def _point(value):
    try:
        return tuple(float(v) for v in value) if len(value) == 2 and all(_number(v) for v in value) else None
    except (TypeError, ValueError, OverflowError):
        return None


@dataclass(frozen=True)
class ShotDetectionConfig:
    possession_support_seconds: float = 0.20
    recent_possession_seconds: float = 0.80
    trajectory_window_seconds: float = 0.40
    minimum_trajectory_seconds: float = 0.12
    max_sample_gap_seconds: float = 0.08
    cooldown_seconds: float = 1.50
    minimum_speed_mps: float = 12.0
    maximum_speed_mps: float = 45.0
    minimum_travel_m: float = 2.50
    minimum_goal_progress_m: float = 2.0
    maximum_goal_distance_m: float = 35.0
    maximum_player_ball_distance_m: float = 3.0
    goal_corridor_margin_m: float = 2.0
    minimum_alignment: float = 0.85
    minimum_straightness: float = 0.85
    minimum_toward_step_fraction: float = 0.80
    minimum_possession_support_ratio: float = 0.60
    confidence_threshold: float = 0.80

    def __post_init__(self):
        for name, value in asdict(self).items():
            if not _number(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")
        for name in ("minimum_alignment", "minimum_straightness", "minimum_toward_step_fraction",
                     "minimum_possession_support_ratio", "confidence_threshold"):
            if getattr(self, name) > 1:
                raise ValueError(f"{name} must be at most 1")
        if self.maximum_speed_mps <= self.minimum_speed_mps:
            raise ValueError("maximum_speed_mps must exceed minimum_speed_mps")
        if self.minimum_trajectory_seconds > self.trajectory_window_seconds:
            raise ValueError("Minimum trajectory duration must fit the trajectory window")

    def thresholds(self, fps):
        if not _number(fps) or fps <= 0:
            raise ValueError("FPS must be positive and finite")
        return {
            "possession_observations": max(2, math.ceil(self.possession_support_seconds * fps)),
            "trajectory_observations": max(3, math.ceil(self.minimum_trajectory_seconds * fps)),
            "minimum_trajectory_frames": max(1, math.ceil(self.minimum_trajectory_seconds * fps)),
            "trajectory_window_frames": math.floor(self.trajectory_window_seconds * fps),
            "recent_possession_frames": math.floor(self.recent_possession_seconds * fps),
            "max_sample_gap_frames": math.floor(self.max_sample_gap_seconds * fps),
            "cooldown_frames": math.ceil(self.cooldown_seconds * fps),
        }


def _calibration(value, pitch_vertices, frame_count):
    """Validate an explicit input-specific goal declaration; no automatic fallback."""
    if not isinstance(value, dict) or value.get("validated_for_input") is not True:
        return None, None, "Input-specific goal/pitch calibration has not been validated."
    if value.get("coordinate_system") != "transformed_pitch_meters":
        return None, None, "Goal coordinates must use the existing transformed pitch coordinates in metres."
    if not isinstance(value.get("source"), str) or not value["source"].strip():
        return None, None, "Calibration must identify its source."
    try:
        vertices = [_point(point) for point in pitch_vertices]
        if len(vertices) != 4 or any(point is None for point in vertices):
            raise ValueError()
        bounds = (min(p[0] for p in vertices), max(p[0] for p in vertices),
                  min(p[1] for p in vertices), max(p[1] for p in vertices))
        if bounds[0] >= bounds[1] or bounds[2] >= bounds[3]:
            raise ValueError()
    except (TypeError, ValueError):
        return None, None, "Finite, nondegenerate transformed pitch bounds are required."
    periods = value.get("periods")
    if not isinstance(periods, list) or not periods:
        return None, None, "No frame-scoped attacking-goal assignments were supplied."
    normalized = []
    for period in periods:
        if not isinstance(period, dict):
            return None, None, "Invalid calibration period."
        start, end = period.get("start_frame"), period.get("end_frame_exclusive")
        if (not isinstance(start, Integral) or isinstance(start, bool) or not isinstance(end, Integral)
                or isinstance(end, bool) or not 0 <= start < end <= frame_count):
            return None, None, "Calibration periods must lie inside the frame history."
        goals = period.get("attacking_goals")
        if not isinstance(goals, dict) or not goals:
            return None, None, "A calibration period has no explicit attacking goals."
        targets = {}
        for team, goal in goals.items():
            team_id = _id(team)
            if team_id not in (1, 2) or not isinstance(goal, dict):
                return None, None, "Goal assignments must reference Team 1 or Team 2."
            center, half_width = _point(goal.get("center")), goal.get("half_width_m")
            if center is None or not _number(half_width) or half_width <= 0:
                return None, None, "Goal center and positive goal half-width must be explicitly measured."
            on_goal_line = abs(center[0] - bounds[0]) <= 0.001 or abs(center[0] - bounds[1]) <= 0.001
            if (not on_goal_line or center[1] - half_width < bounds[2] or center[1] + half_width > bounds[3]):
                return None, None, "Goals must lie on a calibrated longitudinal boundary with the mouth inside its lateral bounds."
            targets[str(team_id)] = {"center": list(center), "half_width_m": float(half_width)}
        if len(targets) == 2 and abs(targets["1"]["center"][0] - targets["2"]["center"][0]) < 0.001:
            return None, None, "Both teams cannot attack the same goal in one period."
        normalized.append({"start_frame": int(start), "end_frame_exclusive": int(end), "attacking_goals": targets})
    normalized.sort(key=lambda p: p["start_frame"])
    if any(a["end_frame_exclusive"] > b["start_frame"] for a, b in zip(normalized, normalized[1:])):
        return None, None, "Calibration periods overlap; attacking direction is ambiguous."
    return {"validated_for_input": True, "coordinate_system": "transformed_pitch_meters",
            "source": value["source"], "periods": normalized}, bounds, None


def _ball(frame, bounds):
    if len(frame) != 1:
        return None
    track = next(iter(frame.values()))
    if not track.get("is_observed", False):
        return None
    point = _point(track.get("position_transformed"))
    if point is None or not (bounds[0] <= point[0] <= bounds[1] and bounds[2] <= point[1] <= bounds[3]):
        return None
    return point


def _owner(players, ball, conflicting_ids, config):
    if not players or not any(p.get("possession_evaluated", False) for p in players.values()):
        return "unknown", None
    holders = [(key, p) for key, p in players.items() if p.get("has_ball", False)]
    if not holders:
        return "free", None
    if len(holders) != 1:
        return "ambiguous", None
    raw_id, player = holders[0]
    player_id, team = _id(raw_id), player.get("team")
    point = _point(player.get("position_transformed"))
    if (player_id is None or player_id in conflicting_ids or team not in (1, 2) or isinstance(team, bool)
            or not player.get("possession_evaluated", False) or point is None
            or math.dist(point, ball) > config.maximum_player_ball_distance_m):
        return "ambiguous", None
    return "owned", (player_id, int(team))


def _trajectory(flight, fps, target, config, thresholds):
    samples = flight["samples"]
    duration_frames = samples[-1][0] - samples[0][0]
    if len(samples) < thresholds["trajectory_observations"] or duration_frames < thresholds["minimum_trajectory_frames"]:
        return None, "short_trajectory"
    start, finish = samples[0][1], samples[-1][1]
    goal = target["center"]
    distances = [math.dist(a[1], b[1]) for a, b in zip(samples, samples[1:])]
    speeds = [distance * fps / (b[0] - a[0]) for distance, a, b in zip(distances, samples, samples[1:])]
    if any(speed > config.maximum_speed_mps for speed in speeds):
        return None, "implausible_jump"
    dx, dy = finish[0] - start[0], finish[1] - start[1]
    travel, path_length = math.hypot(dx, dy), sum(distances)
    net_speed = travel * fps / duration_frames
    if travel < config.minimum_travel_m or net_speed < config.minimum_speed_mps:
        return None, "slow_or_small_movement"
    initial_distance = math.dist(start, goal)
    if initial_distance <= 0 or initial_distance > config.maximum_goal_distance_m:
        return None, "outside_attacking_goal_area"
    progress = initial_distance - math.dist(finish, goal)
    alignment = (dx * (goal[0] - start[0]) + dy * (goal[1] - start[1])) / (travel * initial_distance)
    straightness = travel / path_length if path_length else 0.0
    toward_fraction = sum(math.dist(b[1], goal) < math.dist(a[1], goal)
                          for a, b in zip(samples, samples[1:])) / (len(samples) - 1)
    if (progress < config.minimum_goal_progress_m or alignment < config.minimum_alignment
            or straightness < config.minimum_straightness or toward_fraction < config.minimum_toward_step_fraction):
        return None, "not_consistently_goalward"
    if abs(dx) < 1e-9 or (goal[0] - start[0]) / dx < 1:
        return None, "goal_not_ahead"
    projected_y = start[1] + dy * (goal[0] - start[0]) / dx
    if abs(projected_y - goal[1]) > target["half_width_m"] + config.goal_corridor_margin_m:
        return None, "outside_goal_corridor"
    confidence = round(min(0.95, 0.30 * min(1.0, alignment) + 0.25 * min(1.0, straightness)
                           + 0.20 * min(1.0, net_speed / (2 * config.minimum_speed_mps))
                           + 0.15 * min(1.0, len(samples) / (2 * thresholds["trajectory_observations"]))
                           + 0.10 * max(0.0, 1 - initial_distance / config.maximum_goal_distance_m)), 3)
    if confidence < config.confidence_threshold:
        return None, "below_confidence_threshold"
    return {"net_speed_mps": net_speed, "maximum_segment_speed_mps": max(speeds),
            "displacement_m": travel, "goal_progress_m": progress, "goal_alignment": alignment,
            "straightness": straightness, "toward_step_fraction": toward_fraction,
            "initial_goal_distance_m": initial_distance, "projected_goal_line_y_m": projected_y,
            "observed_samples": len(samples), "duration_seconds": duration_frames / fps,
            "confidence": confidence}, None


def detect_shots(tracks, fps, pitch_vertices=None, *, calibration=None, config=None, pass_events=()):
    """Detect probable shots only from calibrated, observed possession-release trajectories."""
    config = config or ShotDetectionConfig()
    limits = config.thresholds(fps)
    frames, balls = tracks.get("players", []), tracks.get("ball", [])
    validated, bounds, reason = _calibration(calibration, pitch_vertices, len(frames))
    metadata = {
        "status": "skipped_calibration" if reason else "insufficient_data", "reasons": [reason] if reason else [],
        "detector": "heuristic_probable_shot", "detected_shots": 0, "fps": float(fps),
        "config": asdict(config), "frame_thresholds": limits,
        "confidence_method": "weighted_geometry_speed_support_score_not_calibrated_probability",
        "timestamp_semantics": "last_observed_shooter_possession_frame_approximate_release",
        "limitations": ["No guarantee of a shot, shot on target, or goal; crosses and clearances may resemble shots.",
                        "Projected 2D ball speed is approximate, especially for airborne balls.",
                        "Input-specific metric calibration and frame-scoped attacking directions must be supplied explicitly."],
    }
    if reason:
        logger.info("Shot detection skipped: %s", reason)
        return {"events": [], "event_detection": metadata, "calibration": None}
    periods = [None] * len(frames)
    for index, period in enumerate(validated["periods"]):
        periods[period["start_frame"]:period["end_frame_exclusive"]] = [index] * (period["end_frame_exclusive"] - period["start_frame"])
    labels = {}
    for players in frames:
        for key, player in players.items():
            player_id, team = _id(key), player.get("team")
            if player_id is not None and team in (1, 2) and not isinstance(team, bool):
                labels.setdefault(player_id, set()).add(int(team))
    conflicts = {key for key, teams in labels.items() if len(teams) > 1}
    owner_run = flight = None
    previous_period = None
    last_shot_frame = None
    events, rejections = [], Counter()
    observed_frames = supported_sources = 0
    for index, players in enumerate(frames):
        period_id = periods[index]
        if period_id != previous_period or period_id is None:
            owner_run = flight = None
        previous_period = period_id
        if period_id is None:
            continue
        point = _ball(balls[index] if index < len(balls) else {}, bounds)
        if point is None:
            if flight is not None and index - flight["samples"][-1][0] > limits["max_sample_gap_frames"]:
                flight = None
                rejections["ball_tracking_gap"] += 1
            if owner_run is not None and index - owner_run["last"] > limits["max_sample_gap_frames"]:
                owner_run = None
            continue
        observed_frames += 1
        state, owner = _owner(players, point, conflicts, config)
        if state in ("unknown", "ambiguous"):
            owner_run = flight = None
            rejections["unknown_or_ambiguous_possession"] += 1
            continue
        if owner is not None:
            flight = None  # A regained/other owner contradicts free ball flight.
            if (owner_run is None or owner_run["owner"] != owner
                    or index - owner_run["last"] - 1 > limits["max_sample_gap_frames"]):
                owner_run = {"owner": owner, "first": index, "last": index, "point": point, "support": 1}
            else:
                owner_run.update(last=index, point=point, support=owner_run["support"] + 1)
            continue
        if flight is None:
            source = owner_run
            owner_run = None
            if (source is None or source["support"] < limits["possession_observations"]
                    or source["support"] / (source["last"] - source["first"] + 1) < config.minimum_possession_support_ratio
                    or index - source["last"] > limits["recent_possession_frames"]
                    or index - source["last"] - 1 > limits["max_sample_gap_frames"]):
                continue
            supported_sources += 1
            player_id, team = source["owner"]
            target = validated["periods"][period_id]["attacking_goals"].get(str(team))
            if target is None:
                rejections["attacking_goal_unknown_for_team"] += 1
                continue
            if last_shot_frame is not None and source["last"] - last_shot_frame < limits["cooldown_frames"]:
                rejections["cooldown"] += 1
                continue
            contradicted = any(event.get("type") == "pass" and event.get("player_from") == player_id
                               and event.get("team") == team and isinstance(event.get("release_frame"), Integral)
                               and abs(event["release_frame"] - source["last"]) <= limits["max_sample_gap_frames"]
                               and event.get("frame", -1) > source["last"] for event in pass_events)
            if contradicted:
                rejections["confirmed_pass_same_release"] += 1
                continue
            flight = {"source": source, "samples": [(source["last"], source["point"])], "target": target}
        if (index - flight["source"]["last"] > limits["trajectory_window_frames"]
                or index - flight["samples"][-1][0] - 1 > limits["max_sample_gap_frames"]):
            flight = None
            rejections["trajectory_window_or_gap"] += 1
            continue
        flight["samples"].append((index, point))
        evidence, rejection = _trajectory(flight, fps, flight["target"], config, limits)
        if evidence is None:
            rejections[rejection] += 1
            if rejection == "implausible_jump":
                flight = None
            continue
        source = flight["source"]
        event = ShotEvent.at_frame("shot", source["last"], fps, team=source["owner"][1],
                                  player=source["owner"][0], position=source["point"],
                                  confidence=evidence.pop("confidence"), confirmation_frame=index).to_dict()
        event["evidence"] = {**evidence, "attacking_goal": flight["target"],
                             "possession_observations": source["support"], "calibration_period": period_id}
        events.append(event)
        last_shot_frame = source["last"]
        flight = None  # Consume this release; a fresh supported owner is required for another shot.
    metadata.update(status="completed" if supported_sources and observed_frames >= limits["trajectory_observations"] else "insufficient_data",
                    detected_shots=len(events), observed_ball_frames=observed_frames,
                    supported_releases=supported_sources, rejection_evaluations=dict(rejections),
                    conflicting_team_track_ids=sorted(conflicts))
    if metadata["status"] == "insufficient_data":
        metadata["reasons"].append("No sufficiently supported observed possession release/trajectory was available.")
    logger.info("Probable shot detection: %d events, status=%s", len(events), metadata["status"])
    return {"events": events, "event_detection": metadata, "calibration": validated}
