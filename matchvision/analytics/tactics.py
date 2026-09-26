"""Frontend-ready passing networks and observed pitch-space team geometry."""
from collections import Counter
import math
from numbers import Integral, Real

from .formation import estimate_formations


def _id(value):
    if isinstance(value, str):
        try:
            return int(value) if value.isdecimal() else None
        except ValueError:
            return None
    return int(value) if isinstance(value, Integral) and not isinstance(value, bool) and value >= 0 else None


def _bounds(vertices):
    if vertices is None:
        return None
    try:
        if len(vertices) != 4 or any(len(point) != 2 for point in vertices):
            raise ValueError("Expected four pitch vertices")
        points = [[float(value) for value in point] for point in vertices]
        if not all(math.isfinite(value) for point in points for value in point):
            raise ValueError("Pitch vertices must be finite")
        bounds = [min(p[0] for p in points), max(p[0] for p in points),
                  min(p[1] for p in points), max(p[1] for p in points)]
        if bounds[0] >= bounds[1] or bounds[2] >= bounds[3]:
            raise ValueError("Pitch region must have positive extent")
        return bounds
    except (TypeError, OverflowError) as exc:
        raise ValueError("Invalid pitch vertices") from exc


def _point(value, bounds):
    try:
        if len(value) != 2 or any(isinstance(v, bool) or not isinstance(v, Real) for v in value):
            return None
        point = [float(v) for v in value]
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(v) for v in point):
        return None
    if bounds is not None and not (bounds[0] <= point[0] <= bounds[1] and bounds[2] <= point[1] <= bounds[3]):
        return None
    return point


def _average(points):
    return [sum(p[axis] for p in points) / len(points) for axis in (0, 1)] if points else None


def _geometry(frame, index, fps):
    points = list(frame.values())
    center = _average(points)
    spread_available = len(points) >= 2
    return {
        "frame": index, "timestamp": index / fps, "player_ids": sorted(frame),
        "positioned_player_count": len(points), "centroid": center,
        "width_m": max(p[1] for p in points) - min(p[1] for p in points) if spread_available else None,
        "length_m": max(p[0] for p in points) - min(p[0] for p in points) if spread_available else None,
        "compactness_mean_radius_m": sum(math.dist(p, center) for p in points) / len(points) if spread_available else None,
        "full_eleven_visible": len(points) == 11,
    }


def _geometry_summary(timeline):
    summary = {"total_frames": len(timeline), "centroid_frames": 0,
               "spread_frames": 0, "full_eleven_frames": sum(row["full_eleven_visible"] for row in timeline)}
    centers = [row["centroid"] for row in timeline if row["centroid"] is not None]
    summary["average_centroid"] = _average(centers)
    summary["centroid_frames"] = len(centers)
    summary["spread_frames"] = sum(row["width_m"] is not None for row in timeline)
    for name in ("width_m", "length_m", "compactness_mean_radius_m"):
        values = [row[name] for row in timeline if row[name] is not None]
        summary["average_" + name] = sum(values) / len(values) if values else None
    return summary


def build_tactics(tracks, events, fps, pitch_vertices=None, *, formation_config=None, event_detection=None):
    """Collect only supported coordinates; preserve gaps and unknown measurements.

    In this project's transform x is longitudinal (length), y is lateral (width).
    Width is therefore max(y)-min(y), regardless of frontend screen orientation.
    """
    if isinstance(fps, bool) or not isinstance(fps, Real) or not math.isfinite(fps) or fps <= 0:
        raise ValueError("FPS must be positive and finite")
    bounds = _bounds(pitch_vertices)
    frames = tracks.get("players", [])
    records, normalized = {}, []
    skipped_ids = 0
    for frame in frames:
        observations = {}
        for key, track in frame.items():
            player_id = _id(key)
            if player_id is None:
                skipped_ids += 1
                continue
            record = records.setdefault(player_id, {"teams": set(), "points": [], "team_points": [], "observed": 0})
            record["observed"] += 1
            raw_team = track.get("team")
            team = int(raw_team) if raw_team in (1, 2) and not isinstance(raw_team, bool) else None
            if team is not None:
                record["teams"].add(team)
            point = _point(track.get("position_transformed"), bounds)
            if point is not None:
                record["points"].append(point)
                if team is not None:
                    record["team_points"].append(point)
            observations[player_id] = (team, point)
        normalized.append(observations)

    players, memberships = [], {}
    for player_id, record in sorted(records.items()):
        team = next(iter(record["teams"])) if len(record["teams"]) == 1 else None
        memberships[player_id] = team
        players.append({"player_id": player_id, "team_id": team,
                        "average_position": _average(record["points"]),
                        "position_samples": len(record["points"]),
                        "positioned_time_seconds": len(record["points"]) / fps,
                        "observed_frames": record["observed"],
                        "position_coverage": len(record["points"]) / record["observed"],
                        "team_assignment_conflict": len(record["teams"]) > 1})

    connections = {1: Counter(), 2: Counter()}
    duplicates = excluded = 0
    seen = set()
    for event in events:
        if event.get("type") != "pass":
            continue
        source, target = _id(event.get("player_from")), _id(event.get("player_to"))
        team, frame = event.get("team"), _id(event.get("frame"))
        if (team not in (1, 2) or isinstance(team, bool) or source is None or target is None
                or source == target or memberships.get(source) != team or memberships.get(target) != team
                or frame is None or frame >= len(frames)):
            excluded += 1
            continue
        identity = (frame, int(team), source, target)
        if identity in seen:
            duplicates += 1
            continue
        seen.add(identity)
        connections[int(team)][source, target] += 1

    teams = {}
    for team in (1, 2):
        team_frames = [{player_id: point for player_id, (label, point) in frame.items()
                        if label == team and memberships[player_id] == team and point is not None}
                       for frame in normalized]
        timeline = [_geometry(frame, index, fps) for index, frame in enumerate(team_frames)]
        nodes = []
        for player in players:
            if player["team_id"] != team:
                continue
            player_id = player["player_id"]
            points = records[player_id]["team_points"]
            nodes.append({"player_id": player_id, "average_position": _average(points),
                          "position_samples": len(points), "position_available": bool(points),
                          "passes_sent": sum(count for (source, _), count in connections[team].items() if source == player_id),
                          "passes_received": sum(count for (_, target), count in connections[team].items() if target == player_id)})
        edges = [{"source_player": source, "target_player": target, "number_of_passes": count}
                 for (source, target), count in sorted(connections[team].items())]
        teams[str(team)] = {
            "team_id": team,
            "passing_network": {"directed": True, "nodes": nodes, "edges": edges,
                                "total_passes": sum(connections[team].values()),
                                "pass_detection_status": (event_detection or {}).get("status", "not_provided"),
                                "position_method": "average_of_valid_same_team_positions_across_analysis"},
            "timeline": timeline, "summary": _geometry_summary(timeline),
            "formation": estimate_formations(team_frames, fps, bounds, formation_config),
        }
    return {
        "schema_version": "1.0", "players": players, "teams": teams,
        "coordinate_system": {"units": "metres", "longitudinal_axis": "x", "lateral_axis": "y",
                              "frontend_horizontal_axis_for_pitch_width": "y",
                              "bounds": dict(zip(("x_min", "x_max", "y_min", "y_max"), bounds)) if bounds is not None else None},
        "methods": {
            "average_player_position": "arithmetic_mean_of_valid_transformed_observations_no_gap_filling",
            "centroid": "per_frame_mean_of_visible_consistently_assigned_team_positions",
            "width": "max_lateral_y_minus_min_lateral_y_requires_two_players",
            "length": "max_longitudinal_x_minus_min_longitudinal_x_requires_two_players",
            "compactness": "mean_euclidean_distance_to_team_centroid_in_metres_lower_is_tighter_requires_two_players",
            "summary": "equal_weight_mean_over_frames_where_the_metric_is_available",
            "network": "directed_counts_of_detected_pass_events_no_possession_based_edge_invention",
        },
        "quality": {"skipped_invalid_track_ids": skipped_ids, "excluded_pass_events": excluded,
                    "duplicate_pass_events_ignored": duplicates,
                    "conflicting_team_track_ids": [p["player_id"] for p in players if p["team_assignment_conflict"]]},
        "limitations": [
            "Metrics describe visible players within the calibrated region, not necessarily the full team.",
            "Missing positions are excluded, not treated as zero; changing visibility changes team geometry.",
            "Goalkeepers are included in geometry; roles are unavailable in the original tracks.",
            "Track fragmentation, identity switches and calibration errors affect all estimates.",
            "Whole-analysis player means and network positions can blur substitutions, movement and side changes.",
            "Formation labels are conservative spatial hypotheses, not verified tactical intent.",
        ],
    }

