"""Analytics consumes enriched tracks without rerunning detection."""
from ..progress import report_progress
from .events import MatchEvent, PassEvent, ShotEvent, merge_event_detections
from .heatmaps import build_heatmaps
from .statistics import summarize_statistics
from .tactics import build_tactics
from .formation import FormationConfig
from .shot_detection import ShotDetectionConfig, detect_shots
from .pass_detection import PassDetectionConfig, add_pass_statistics, detect_passes


def build_analytics(tracks, fps, possession, colors, pitch_vertices, output_directory=None,
                    *, pass_config=None, formation_config=None, shot_config=None, shot_calibration=None,
                    progress_callback=None):
    result = summarize_statistics(tracks.get("players", []), fps, possession, colors)
    report_progress(progress_callback, 78, "Generating heatmaps")
    result["heatmaps"] = build_heatmaps(tracks, fps, pitch_vertices, output_directory)
    report_progress(progress_callback, 81, "Detecting passes")
    detection = detect_passes(tracks, fps, config=pass_config)

    report_progress(progress_callback, 84, "Detecting shots")
    shots = detect_shots(tracks, fps, pitch_vertices, calibration=shot_calibration,
                         config=shot_config, pass_events=detection["events"])
    result.update(merge_event_detections(detection, shots))
    add_pass_statistics(result["players"], result["teams"],
                        {"events": result["events"], "event_detection": detection["event_detection"]})
    result["possession"]["known_stable_player_frames"] = detection["event_detection"]["known_stable_possession_frames"]
    result["possession"]["player_time_method"] = "stable_observed_owner_frames_only_no_interpolation_or_gap_filling"
    report_progress(progress_callback, 87, "Analysing tactics")
    result["tactics"] = build_tactics(tracks, result["events"], fps, pitch_vertices,
                                      formation_config=formation_config,
                                      event_detection=detection["event_detection"])
    return result


__all__ = ["MatchEvent", "PassEvent", "PassDetectionConfig", "detect_passes",
           "build_analytics", "build_heatmaps", "summarize_statistics", "build_tactics", "FormationConfig",
           "ShotEvent", "ShotDetectionConfig", "detect_shots"]




