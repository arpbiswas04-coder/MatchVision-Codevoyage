"""Coverage-qualified time windows of visible team geometry."""
from collections import Counter
from dataclasses import replace
import math
import os

from .formation import FormationConfig, UNKNOWN_FORMATION, _window


def temporal_tactics(team_frames, timeline, fps, bounds, formation_config=None):
    seconds = float(os.getenv("MATCHVISION_TACTICAL_WINDOW_SECONDS", "10"))
    minimum_players = int(os.getenv("MATCHVISION_TACTICAL_MIN_PLAYERS", "6"))
    minimum_coverage = float(os.getenv("MATCHVISION_TACTICAL_MIN_COVERAGE", "0.5"))
    if not math.isfinite(seconds) or seconds < 2 or minimum_players < 2 or not 0 < minimum_coverage <= 1:
        raise ValueError("Invalid tactical window/coverage configuration")
    config = formation_config or FormationConfig()
    config = replace(config, window_seconds=seconds,
                     minimum_window_seconds=min(config.minimum_window_seconds, seconds),
                     minimum_player_seconds=min(config.minimum_player_seconds, seconds))
    step = max(1, round(seconds * fps))
    windows, measured = [], []
    for start in range(0, len(timeline), step):
        rows = timeline[start:start + step]
        usable = [row for row in rows if row["positioned_player_count"] >= minimum_players]
        available = bool(rows) and len(rows) / fps >= min(5, seconds) and len(usable) / len(rows) >= minimum_coverage
        shape = _window(team_frames[start:start + step], start, fps, bounds, config)
        row = {
            "start_seconds": start / fps, "end_seconds": (start + len(rows)) / fps,
            "available": available, "coverage_percentage": 100 * len(usable) / len(rows),
            "average_visible_players": sum(item["positioned_player_count"] for item in rows) / len(rows),
            "formation": {"label": shape["label"], "status": shape["status"],
                          "support_percentage": 100 * shape["joint_coverage"], "reasons": shape["reasons"]},
        }
        for source, target in (("width_m", "average_width_m"), ("length_m", "average_length_m"),
                               ("compactness_mean_radius_m", "average_compactness_mean_radius_m")):
            row[target] = sum(item[source] for item in usable) / len(usable) if available else None
        row["centroid"] = [sum(item["centroid"][axis] for item in usable) / len(usable)
                           for axis in (0, 1)] if available else None
        if available:
            measured.extend(usable)
        windows.append(row)
    supported = [row for row in windows if row["formation"]["status"] == "heuristic_estimate"]
    durations = Counter()
    for row in supported:
        durations[row["formation"]["label"]] += row["end_seconds"] - row["start_seconds"]
    duration = len(timeline) / fps
    candidate = durations.most_common(1)[0][0] if durations else None
    winning_windows = [row for row in supported if row["formation"]["label"] == candidate]
    support = durations[candidate] / duration if candidate is not None and duration else 0
    accepted = len(winning_windows) >= 2 and support >= config.minimum_summary_coverage
    formation = {
        "label": candidate if accepted else UNKNOWN_FORMATION,
        "status": "heuristic_estimate" if accepted else "insufficient_data",
        "support_percentage": 100 * support,
        "supported_window_count": len(winning_windows),
        "reason": "Most frequent time-weighted supported shape; at least two windows and sufficient match coverage."
                  if accepted else "No repeated formation hypothesis with sufficient match-time support.",
        "support_method": "fraction_of_match_time_supporting_dominant_label_not_probability",
    }
    summary = {
        "average_centroid": [sum(row["centroid"][axis] for row in measured) / len(measured) for axis in (0, 1)] if measured else None,
        "coverage_percentage": 100 * len(measured) / len(timeline) if timeline else 0,
        "minimum_visible_players": minimum_players, "minimum_window_coverage": minimum_coverage,
        "window_seconds": seconds, "most_common_supported_formation": formation,
    }
    for field, name in (("width_m", "width_m"), ("length_m", "length_m"),
                        ("compactness_mean_radius_m", "compactness_mean_radius_m")):
        values = [row[field] for row in measured]
        summary["average_" + name] = sum(values) / len(values) if values else None
        summary["minimum_" + name] = min(values) if values else None
        summary["maximum_" + name] = max(values) if values else None
    available = [row for row in windows if row["available"]]
    for name, field, reverse in (("widest_period", "average_width_m", True),
                                 ("narrowest_period", "average_width_m", False),
                                 ("most_compact_period", "average_compactness_mean_radius_m", False)):
        selected = sorted(available, key=lambda row: row[field], reverse=reverse)
        summary[name] = {key: selected[0][key] for key in ("start_seconds", "end_seconds", field)} if selected else None
    return {"summary": summary, "windows": windows}

