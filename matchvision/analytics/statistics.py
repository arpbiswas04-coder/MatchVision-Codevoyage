"""Observed player/team summaries; absent measurements are never filled with zero."""
from collections import Counter
import math


def _measurement(value):
    if value is None or isinstance(value, (bool, str)):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def _mean(values):
    return sum(values) / len(values) if values else None


def summarize_statistics(player_frames, fps, possession, colors):
    """Speeds are frame-weighted per player; team speed is the mean of player means.

    Distance is the maximum available cumulative estimator reading, not a sum
    of repeated frame readings. Times count supported frames / source FPS and
    exclude gaps between sightings. Player possession excludes carried-forward
    team possession and frames where the ball was only interpolated.
    """
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("FPS must be positive and finite")
    records = {}
    for frame in player_frames:
        for player_id, track in frame.items():
            record = records.setdefault(int(player_id), {
                "teams": set(), "speeds": [], "distances": [], "observed": 0,
                "possession_evaluated": 0, "possession": 0,
            })
            record["observed"] += 1
            team = track.get("team")
            if team in (1, 2):
                record["teams"].add(int(team))
            speed = _measurement(track.get("speed"))
            distance = _measurement(track.get("distance"))
            if speed is not None:
                record["speeds"].append(speed)
            if distance is not None:
                record["distances"].append(distance)
            if track.get("possession_evaluated"):
                record["possession_evaluated"] += 1
                record["possession"] += int(bool(track.get("has_ball", False)))

    players = []
    for player_id, record in sorted(records.items()):
        players.append({
            "player_id": player_id,
            "team_id": next(iter(record["teams"])) if len(record["teams"]) == 1 else None,
            "observed_frames": record["observed"],
            "tracked_time_seconds": record["observed"] / fps,
            "distance_m": max(record["distances"]) if record["distances"] else None,
            "max_speed_kmh": max(record["speeds"]) if record["speeds"] else None,
            "average_speed_kmh": _mean(record["speeds"]),
            "speed_measured_frames": len(record["speeds"]),
            "distance_measured_frames": len(record["distances"]),
            "possession_time_seconds": (record["possession"] / fps
                                        if record["possession_evaluated"] else None),
            "possession_frames": record["possession"] if record["possession_evaluated"] else None,
            "possession_evaluated_frames": record["possession_evaluated"],
        })

    counts = Counter(int(team) if team in (1, 2) else 0 for team in possession)
    known = counts[1] + counts[2]
    percentages = {str(team): 100 * counts[team] / known if known else None for team in (1, 2)}
    teams = []
    for team in (1, 2):
        members = [p for p in players if p["team_id"] == team]
        distances = [p["distance_m"] for p in members if p["distance_m"] is not None]
        speeds = [p["average_speed_kmh"] for p in members if p["average_speed_kmh"] is not None]
        color = colors.get(team, colors.get(str(team)))
        color = [_measurement(channel) for channel in color] if color is not None else None
        if color is not None and (len(color) != 3 or any(channel is None for channel in color)):
            color = None
        teams.append({
            "team_id": team, "color_bgr": color,
            "possession_percentage": percentages[str(team)],
            "total_distance_m": sum(distances) if distances else None,
            "average_player_speed_kmh": _mean(speeds),
            "tracked_player_count": len(members),
            "distance_measured_players": len(distances),
            "speed_measured_players": len(speeds),
        })
    return {
        "players": players, "teams": teams,
        "possession": {
            "method": "nearest_player_with_previous_team_carried_forward",
            "known_frames": known, "unknown_frames": counts[0],
            "team_percentages": percentages,
            "player_time_method": "observed_ball_assignment_frames_divided_by_fps",
        },
        "statistics_methods": {
            "distance": "maximum_available_cumulative_distance_per_track",
            "player_average_speed": "mean_of_valid_frame_speed_estimates",
            "team_average_speed": "equal_weight_mean_of_available_player_average_speeds",
            "tracked_time": "observed_frames_divided_by_fps_excluding_detection_gaps",
            "team_membership": "unique_known_team_per_track_otherwise_null",
            "coverage": "partial_measurements_only_not_extrapolated_to_unobserved_time",
            "identity": "tracking_ids_may_fragment_or_switch_not_unique_real_world_players",
        },
    }
