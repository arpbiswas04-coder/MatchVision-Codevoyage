"""Convert NumPy-backed tracking data into the frontend-facing result schema."""
import math
import numpy as np


def to_json_value(value):
    if isinstance(value, np.ndarray):
        return to_json_value(value.tolist())
    if isinstance(value, np.generic):
        return to_json_value(value.item())
    if isinstance(value, dict):
        return {str(key): to_json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_json_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def build_results(analysis_id, metadata, tracks, movement, colors, possession, directory, warnings,
                  *, pitch_vertices=None, pass_config=None, formation_config=None,
                  shot_config=None, shot_calibration=None, progress_callback=None):
    from view_transformer import ViewTransformer
    from .analytics import build_analytics

    if pitch_vertices is None:
        pitch_vertices = ViewTransformer().target_vertices
    analytics = build_analytics(tracks, metadata["fps"], possession, colors, pitch_vertices, directory,
                                pass_config=pass_config, formation_config=formation_config,
                                shot_config=shot_config, shot_calibration=shot_calibration,
                                progress_callback=progress_callback)
    result_warnings = list(warnings) + analytics["heatmaps"]["warnings"]
    return to_json_value({
        "schema_version": "2.3", "analysis_id": analysis_id, "status": "completed",
        "match": {"analysis_id": analysis_id, **metadata},
        "video": metadata,
        "output_video": str(directory / "output_video.avi"),
        "artifacts": {"output_directory": str(directory),
                      "annotated_video": str(directory / "output_video.avi"),
                      "analysis_json": str(directory / "analysis.json")},
        "units": {"speed": "km/h", "distance": "m", "time": "seconds", "color": "BGR"},
        "calibration": {"source": "original_fixed_pitch", "validated_for_input": False},
        **analytics,
        "frames": [{"frame_index": index, "timestamp_seconds": index / metadata["fps"],
                    "possession_team_id": possession[index] or None,
                    "camera_movement": movement[index],
                    **{kind: frames[index] for kind, frames in tracks.items()}}
                   for index in range(metadata["frame_count"])],
        "warnings": result_warnings,
    })




