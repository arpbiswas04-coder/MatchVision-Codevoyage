"""Analytics consumes enriched tracks without rerunning detection."""
from .events import MatchEvent, PassEvent, ShotEvent, merge_event_detections
from .heatmaps import build_heatmaps
from .statistics import summarize_statistics
from .tactics import build_tactics
from .formation import FormationConfig
from .shot_detection import ShotDetectionConfig, detect_shots
from .pass_detection import PassDetectionConfig, add_pass_statistics, detect_passes


def build_analytics(tracks, fps, possession, colors, pitch_vertices, output_directory=None,
                    *, pass_config=None, formation_config=None, shot_config=None, shot_calibration=None):
    result = summarize_statistics(tracks.get("players", []), fps, possession, colors)
    result["heatmaps"] = build_heatmaps(tracks, fps, pitch_vertices, output_directory)
    detection = detect_passes(tracks, fps, config=pass_config)
    add_pass_statistics(result["players"], result["teams"], detection)
    shots = detect_shots(tracks, fps, pitch_vertices, calibration=shot_calibration,
                         config=shot_config, pass_events=detection["events"])
    result.update(merge_event_detections(detection, shots))
    result["tactics"] = build_tactics(tracks, result["events"], fps, pitch_vertices,
                                      formation_config=formation_config,
                                      event_detection=detection["event_detection"])
    return result


__all__ = ["MatchEvent", "PassEvent", "PassDetectionConfig", "detect_passes",
           "build_analytics", "build_heatmaps", "summarize_statistics", "build_tactics", "FormationConfig",
           "ShotEvent", "ShotDetectionConfig", "detect_shots"]


