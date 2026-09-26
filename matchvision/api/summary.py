"""Bounded dashboard projection of already sanitized API results; no frame arrays."""
from collections import Counter

PLAYER_LIMIT = 500
EVENT_LIMIT = 100
MEDIA_LIMIT = 500


def scalars(value):
    return {key: item for key, item in value.items()
            if item is None or isinstance(item, (str, int, float, bool))}


def fields(value, names):
    return {name: value[name] for name in names if name in value}


def build_summary(result):
    analysis_id = result["analysis_id"]
    base = f"/api/matches/{analysis_id}"
    players = result.get("players", [])
    events = result.get("events", [])
    tactics = result.get("tactics", {})
    media = result.get("media", {})
    teams = {}
    for key, team in tactics.get("teams", {}).items():
        formation = team.get("formation", {})
        network = team.get("passing_network", {})
        temporal = team.get("temporal", {})
        windows = temporal.get("windows", [])
        # Preserve temporal coverage across long recordings rather than only the start.
        indices = sorted({round(i * (len(windows) - 1) / 59) for i in range(60)}) if len(windows) > 60 else range(len(windows))
        stats = next((item for item in result.get("teams", []) if item.get("team_id") == team.get("team_id")), {})
        teams[key] = {
            "team_id": team.get("team_id"),
            "temporal": {"summary": temporal.get("summary", {}),
                         "windows": [windows[index] for index in indices],
                         "total_windows": len(windows), "omitted_windows": max(0, len(windows) - 60)},
            "geometry": fields(team.get("summary", {}), (
                "total_frames", "centroid_frames", "spread_frames", "full_eleven_frames",
                "average_centroid", "average_width_m", "average_length_m",
                "average_compactness_mean_radius_m")),
            "formation": fields(formation, ("label", "status", "reason", "supported_time_fraction", "limitations")),
            "passing_network": {"total_passes": stats.get("total_detected_successful_passes"),
                                "connection_count": len(network.get("edges", [])) if stats.get("pass_statistics_available") else None,
                                "details_url": base + "/results"},
        }
    player_fields = ("player_id", "team_id", "tracked_time_seconds", "observed_frames",
                     "distance_m", "max_speed_kmh", "average_speed_kmh",
                     "possession_time_seconds", "possession_frames", "possession_percentage_of_known_possession",
                     "successful_passes", "passes_received", "passes_sent_to", "passes_received_from", "pass_statistics_available")
    event_fields = ("type", "timestamp", "frame", "team", "player", "player_from", "player_to",
                    "confidence", "position", "from_position", "to_position", "distance", "classification")
    highlight_fields = ("event_type", "timestamp", "start", "end", "confidence", "video_path",
                        "asset_id", "source", "backend", "audio_mode", "duration_seconds")
    heatmaps = result.get("heatmaps", {})
    # Counts reflect all results, independently of the dashboard list limits.
    counts = {
        "players": len(players), "events": len(events),
        "events_by_type": dict(Counter(event.get("type", "unknown") for event in events)),
        "player_heatmap_images": sum(bool(value.get("image_path"))
                                    for value in heatmaps.get("players", {}).values()),
        "heatmap_images": len(media.get("heatmaps", [])),
        "highlights": len(result.get("highlights", [])),
    }
    detection = result.get("event_detection", {})
    shots = detection.get("shots", {})
    event_available = bool(events) or detection.get("status") == "completed" or shots.get("status") == "completed"
    counts["recorded_event_count"] = len(events)
    counts["events"] = len(events) if event_available else None
    counts["events_by_type"] = {
        "pass": sum(event.get("type") == "pass" for event in events) if detection.get("status") == "completed" else None,
        "shot": sum(event.get("type") == "shot" for event in events) if shots.get("status") == "completed" else None,
    }
    highlight_available = bool(result.get("highlights")) or (
        result.get("highlight_generation", {}).get("status") in ("completed", "no_eligible_events")
        and shots.get("status") == "completed")
    counts["highlights"] = len(result.get("highlights", [])) if highlight_available else None
    summary = {
        "availability": {"events": event_available, "highlights": highlight_available},
        "schema_version": "1.0", "analysis_id": analysis_id, "status": result.get("status"),
        "match": scalars(result.get("match", {})), "video": scalars(result.get("video", {})),
        "duration_seconds": result.get("video", {}).get("duration_seconds"),
        "units": result.get("units", {}),
        "teams": [scalars(team) | fields(team, ("color_bgr",)) for team in result.get("teams", [])],
        "players": [fields(player, player_fields) for player in players[:PLAYER_LIMIT]],
        "possession": fields(result.get("possession", {}), (
            "method", "known_frames", "unknown_frames", "team_percentages", "player_time_method")),
        "events": [fields(event, event_fields) for event in events[-EVENT_LIMIT:]],
        "counts": counts,
        "tactics": {"teams": teams, "limitations": tactics.get("limitations", [])[:20]},
        "heatmaps": media.get("heatmaps", [])[:MEDIA_LIMIT],
        "heatmap_rendering": heatmaps.get("rendering", {}),
        "highlights": [fields(clip, highlight_fields) for clip in result.get("highlights", [])[:MEDIA_LIMIT]],
        "annotated_video": media.get("video", {}),
        "tracking": fields(result.get("tracking", {}), (
            "method", "raw_player_track_count", "logical_player_count", "accepted_links", "limitations")),
        "event_detection": {
            "passes": fields(result.get("event_detection", {}), ("status", "detected_passes", "limitations")),
            "shots": fields(result.get("event_detection", {}).get("shots", {}),
                            ("status", "detected_shots", "reason", "reasons", "limitations")),
        },
        "highlight_generation": fields(result.get("highlight_generation", {}),
                                      ("status", "eligible_events", "failed_windows", "warnings")),
        "warnings": result.get("warnings", [])[:30],
        "statistics_methods": result.get("statistics_methods", {}),
        "full_results_url": base + "/results",
        "lists": {
            "players": {"limit": PLAYER_LIMIT, "omitted": max(0, len(players) - PLAYER_LIMIT)},
            "events": {"limit": EVENT_LIMIT, "selection": "latest_chronological",
                       "omitted": max(0, len(events) - EVENT_LIMIT)},
            "heatmaps": {"limit": MEDIA_LIMIT, "omitted": max(0, counts["heatmap_images"] - MEDIA_LIMIT)},
            "highlights": {"limit": MEDIA_LIMIT, "omitted": max(0, len(result.get("highlights", [])) - MEDIA_LIMIT)},
        },
    }
    return summary


