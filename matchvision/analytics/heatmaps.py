"""Pitch-space occupancy histograms and PNG previews, using NumPy and OpenCV."""
import logging
import math
from pathlib import Path

import cv2
import numpy as np
from .pitch_rendering import render_pitch_heatmap

logger = logging.getLogger(__name__)


def _position(track, bounds):
    try:
        point = np.asarray(track.get("position_transformed"), dtype=float)
    except (TypeError, ValueError):
        return None
    if point.shape != (2,) or not np.isfinite(point).all():
        return None
    x, y = map(float, point)
    if not (bounds[0] <= x <= bounds[1] and bounds[2] <= y <= bounds[3]):
        return None
    return [x, y]


_render = render_pitch_heatmap


def build_heatmaps(tracks, fps, pitch_vertices, output_directory=None, bins=(24, 68)):
    """Collect valid transformed samples; bin counts are indexed [y][x].

    Ball samples require is_observed=True. Interpolated or unknown-provenance
    ball positions never masquerade as measured locations. A missing heatmap
    has sample_count=0, available=False, empty samples and no image.
    """
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("FPS must be positive and finite")
    vertices = np.asarray(pitch_vertices, dtype=float)
    if vertices.shape != (4, 2) or not np.isfinite(vertices).all():
        raise ValueError("Pitch vertices must be four finite x/y coordinates")
    bounds = [float(vertices[:, 0].min()), float(vertices[:, 0].max()),
              float(vertices[:, 1].min()), float(vertices[:, 1].max())]
    if bounds[1] <= bounds[0] or bounds[3] <= bounds[2]:
        raise ValueError("Pitch bounds must have positive width and height")
    x_edges = np.linspace(bounds[0], bounds[1], bins[0] + 1)
    y_edges = np.linspace(bounds[2], bounds[3], bins[1] + 1)
    players, teams, ball = {}, {"1": [], "2": []}, []
    exclusions = {"player_positions_missing_or_outside_region": 0,
                  "ball_unobserved_or_unknown_provenance": 0,
                  "ball_positions_missing_or_outside_region": 0}
    for frame_index, frame in enumerate(tracks.get("players", [])):
        for player_id, track in frame.items():
            samples = players.setdefault(str(int(player_id)), [])
            point = _position(track, bounds)
            if point is None:
                exclusions["player_positions_missing_or_outside_region"] += 1
                continue
            sample = {"frame": frame_index, "x": point[0], "y": point[1]}
            samples.append(sample)
            if track.get("team") in (1, 2):
                teams[str(int(track["team"]))].append({**sample, "player_id": int(player_id)})
    for frame_index, frame in enumerate(tracks.get("ball", [])):
        for track in frame.values():
            if not track.get("is_observed", False):
                exclusions["ball_unobserved_or_unknown_provenance"] += 1
                continue
            point = _position(track, bounds)
            if point is None:
                exclusions["ball_positions_missing_or_outside_region"] += 1
                continue
            ball.append({"frame": frame_index, "x": point[0], "y": point[1]})

    warnings = []
    image_directory = Path(output_directory) / "heatmaps" if output_directory is not None else None

    def make_map(samples, filename, title):
        counts = np.zeros((bins[1], bins[0]), dtype=np.int64)
        if samples:
            counts = np.histogram2d([p["y"] for p in samples], [p["x"] for p in samples],
                                    bins=(y_edges, x_edges))[0].astype(np.int64)
        image_path = None
        if samples and image_directory is not None:
            try:
                image_directory.mkdir(parents=True, exist_ok=True)
                path = image_directory / filename
                _render(counts, path, title, bounds, len(samples), fps)
                image_path = str(path.resolve())
            except (OSError, cv2.error) as exc:
                message = f"Heatmap image unavailable ({filename}): {exc}"
                logger.warning(message)
                warnings.append(message)
        return {
            "available": bool(samples), "sample_count": len(samples), "samples": samples,
            "counts": counts.tolist(), "occupancy_seconds": (counts / fps).tolist(),
            "image_path": image_path,
        }

    return {
        "coordinate_system": "transformed_pitch_meters",
        "rendering": {"style": "dark_pitch_region", "horizontal_axis": "y", "vertical_axis": "x_increasing_up",
                      "full_pitch_registration": False, "density_smoothing": "display_only",
                      "reference_pitch": "normalized_density_context_not_global_coordinates"},
        "calibration": "original_fixed_pitch_region_unvalidated_for_input",
        "bounds": {"x_min": bounds[0], "x_max": bounds[1], "y_min": bounds[2], "y_max": bounds[3]},
        "grid": {"columns": bins[0], "rows": bins[1], "array_order": "y_then_x",
                 "x_edges": x_edges.tolist(), "y_edges": y_edges.tolist()},
        "method": "observed_sample_histogram_without_smoothing",
        "seconds_method": "sample_counts_divided_by_fps_team_values_are_player_seconds",
        "ball_policy": "observed_only_excludes_interpolation_and_unknown_provenance",
        "players": {key: make_map(samples, f"player_{key}.png", f"Player {key} movement")
                    for key, samples in sorted(players.items(), key=lambda pair: int(pair[0]))},
        "teams": {key: make_map(samples, f"team_{key}.png", f"Team {key} movement")
                  for key, samples in teams.items()},
        "ball": make_map(ball, "ball.png", "Ball observed locations"),
        "excluded_samples": exclusions, "warnings": warnings,
    }


