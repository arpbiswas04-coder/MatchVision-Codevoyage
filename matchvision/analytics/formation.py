"""Explainable, conservative formation hypotheses from windowed average positions."""
from dataclasses import asdict, dataclass
import math
from numbers import Real

UNKNOWN_FORMATION = "Unknown / insufficient tracking data"
SUPPORTED_FORMATIONS = {(4, 4, 2), (4, 3, 3), (4, 2, 3, 1)}


@dataclass(frozen=True)
class FormationConfig:
    window_seconds: float = 30.0
    minimum_window_seconds: float = 10.0
    minimum_player_seconds: float = 3.0
    minimum_player_coverage: float = 0.80
    minimum_joint_coverage: float = 0.70
    minimum_calibrated_length_m: float = 70.0
    minimum_calibrated_width_m: float = 45.0
    maximum_player_rms_radius_m: float = 12.0
    goalkeeper_gap_m: float = 8.0
    goalkeeper_end_fraction: float = 0.15
    line_gap_m: float = 6.0
    maximum_line_depth_m: float = 8.0
    minimum_summary_coverage: float = 0.60

    def __post_init__(self):
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")
        for name in ("minimum_player_coverage", "minimum_joint_coverage",
                     "goalkeeper_end_fraction", "minimum_summary_coverage"):
            if getattr(self, name) > 1:
                raise ValueError(f"{name} must be at most 1")
        if self.minimum_window_seconds > self.window_seconds:
            raise ValueError("minimum_window_seconds cannot exceed window_seconds")
        if self.minimum_player_seconds > self.minimum_window_seconds:
            raise ValueError("minimum_player_seconds cannot exceed minimum_window_seconds")


def _window(frames, start, fps, bounds, config):
    duration = len(frames) / fps
    result = {
        "start_frame": start, "end_frame_exclusive": start + len(frames),
        "start_seconds": start / fps, "duration_seconds": duration,
        "label": UNKNOWN_FORMATION, "status": "insufficient_data", "reasons": [],
        "eligible_player_ids": [], "joint_coverage": 0.0,
        "goalkeeper_candidate_id": None, "longitudinal_direction": None,
        "average_positions": [], "lines": [],
    }
    if bounds is None:
        result["reasons"].append("Calibrated pitch-region bounds are unavailable.")
    elif (bounds[1] - bounds[0] < config.minimum_calibrated_length_m
          or bounds[3] - bounds[2] < config.minimum_calibrated_width_m):
        result["reasons"].append("Calibrated region is too small to support a full-team formation.")
    if len(frames) < math.ceil(config.minimum_window_seconds * fps):
        result["reasons"].append("Window is too short for a formation estimate.")
    if result["reasons"]:
        return result

    samples = {}
    for frame in frames:
        for player_id, point in frame.items():
            samples.setdefault(player_id, []).append(point)
    required = max(math.ceil(config.minimum_player_seconds * fps),
                   math.ceil(config.minimum_player_coverage * len(frames)))
    eligible = {key: points for key, points in samples.items() if len(points) >= required}
    result["eligible_player_ids"] = sorted(eligible)
    if len(eligible) != 11:
        result["reasons"].append("Exactly eleven consistently tracked identities, including a goalkeeper candidate, are required.")
        return result
    ids = set(eligible)
    joint = sum(set(frame) == ids for frame in frames) / len(frames)
    result["joint_coverage"] = joint
    if joint < config.minimum_joint_coverage:
        result["reasons"].append("The same eleven identities are not jointly visible often enough.")
        return result

    averages = []
    for player_id, points in eligible.items():
        mean = [sum(p[axis] for p in points) / len(points) for axis in (0, 1)]
        radius = math.sqrt(sum((p[0] - mean[0]) ** 2 + (p[1] - mean[1]) ** 2 for p in points) / len(points))
        averages.append({"player_id": player_id, "position": mean,
                         "sample_count": len(points), "rms_radius_m": radius})
    averages.sort(key=lambda item: (item["position"][0], item["player_id"]))
    result["average_positions"] = averages
    if any(item["rms_radius_m"] > config.maximum_player_rms_radius_m for item in averages):
        result["reasons"].append("Player positions vary too much to support one stable shape in this window.")
        return result

    # Do not discard an arbitrary player as goalkeeper: require a uniquely isolated
    # longitudinal extreme near an end of the calibrated region.
    extent = bounds[1] - bounds[0]
    low_goalkeeper = (averages[0]["position"][0] - bounds[0] <= config.goalkeeper_end_fraction * extent
                      and averages[1]["position"][0] - averages[0]["position"][0] >= config.goalkeeper_gap_m)
    high_goalkeeper = (bounds[1] - averages[-1]["position"][0] <= config.goalkeeper_end_fraction * extent
                       and averages[-1]["position"][0] - averages[-2]["position"][0] >= config.goalkeeper_gap_m)
    if low_goalkeeper == high_goalkeeper:
        result["reasons"].append("A unique isolated goalkeeper-side candidate cannot be identified.")
        return result
    ordered = averages if low_goalkeeper else list(reversed(averages))
    result["goalkeeper_candidate_id"] = ordered[0]["player_id"]
    result["longitudinal_direction"] = "increasing_x" if low_goalkeeper else "decreasing_x"
    groups = []
    for player in ordered[1:]:
        if not groups or abs(player["position"][0] - groups[-1][-1]["position"][0]) >= config.line_gap_m:
            groups.append([])
        groups[-1].append(player)
    result["lines"] = [{
        "player_ids": [player["player_id"] for player in group],
        "mean_longitudinal_x_m": sum(p["position"][0] for p in group) / len(group),
        "longitudinal_depth_m": max(p["position"][0] for p in group) - min(p["position"][0] for p in group),
    } for group in groups]
    if any(line["longitudinal_depth_m"] > config.maximum_line_depth_m for line in result["lines"]):
        result["reasons"].append("At least one inferred line is too spread longitudinally.")
        return result
    shape = tuple(len(group) for group in groups)
    if shape not in SUPPORTED_FORMATIONS:
        result["reasons"].append("Separated lines do not match a supported formation; no nearest-template guess was made.")
        return result
    result.update(label="-".join(map(str, shape)), status="heuristic_estimate")
    result["reasons"] = ["Eleven co-visible stable tracks, one isolated goalkeeper-side candidate, and separated outfield lines support this shape."]
    return result


def estimate_formations(team_frames, fps, bounds, config=None):
    config = config or FormationConfig()
    if isinstance(fps, bool) or not isinstance(fps, Real) or not math.isfinite(fps) or fps <= 0:
        raise ValueError("FPS must be positive and finite")
    window_frames = max(1, math.ceil(config.window_seconds * fps))
    windows = [_window(team_frames[start:start + window_frames], start, fps, bounds, config)
               for start in range(0, len(team_frames), window_frames)]
    supported = [window for window in windows if window["status"] == "heuristic_estimate"]
    coverage = sum(window["duration_seconds"] for window in supported) / (len(team_frames) / fps) if team_frames else 0.0
    labels = {window["label"] for window in supported}
    agreed = len(labels) == 1 and coverage >= config.minimum_summary_coverage
    return {
        "label": next(iter(labels)) if agreed else UNKNOWN_FORMATION,
        "status": "heuristic_estimate" if agreed else "insufficient_data",
        "reason": "Supported windows agree with sufficient temporal coverage." if agreed
                  else "No sufficiently covered, consistent formation hypothesis; see per-window reasons.",
        "supported_time_fraction": coverage, "windows": windows,
        "method": "windowed_average_positions_isolated_goalkeeper_and_longitudinal_gap_groups",
        "config": asdict(config), "window_frames": window_frames,
        "supported_shapes": ["4-4-2", "4-3-3", "4-2-3-1"],
        "limitations": "Goalkeeper and orientation are inferred, not verified roles. This describes spatial shape, not tactical intent or a confirmed formation.",
    }
