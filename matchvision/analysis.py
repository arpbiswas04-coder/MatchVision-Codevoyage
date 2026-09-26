"""Orchestrate the existing football analysis components for one isolated run."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import numpy as np

from util import read_video, save_video
from trackers import Tracker
from team_assigner import TeamAssigner
from player_ball_assigner import PlayerBallAssigner
from camera_movement_estimator import CameraMovementEstimator
from view_transformer import ViewTransformer
from speed_and_distance_estimator import SpeedAndDistanceEstimator
from .results import build_results

logger = logging.getLogger(__name__)
MODEL_PATH = Path(__file__).resolve().parents[1] / "model" / "best.pt"


class AnalysisError(RuntimeError):
    """A failed analysis; the original exception is available as __cause__."""


def _assign_teams(frames, tracks, warnings):
    assigner = TeamAssigner(legacy_player_override=False)
    # Some videos begin before any players appear. Fit on the first usable frame.
    for frame, players in zip(frames, tracks["players"]):
        usable = {}
        for player_id, player in players.items():
            try:
                assigner.get_player_color(frame, player["bbox"])
            except ValueError:
                continue
            usable[player_id] = player
        if len(usable) >= 2:
            assigner.assign_team_color(frame, usable)
            break
    if not assigner.team_colors:
        warnings.append("No frame had two usable players; team assignment is unavailable.")
        return assigner
    for frame, players in zip(frames, tracks["players"]):
        for player_id, player in players.items():
            try:
                team = assigner.get_player_team(frame, player["bbox"], player_id)
            except ValueError:
                continue
            player.update(team=team, team_color=assigner.team_colors[team])
    return assigner


def analyze_match(input_video_path, output_directory, *, pass_config=None, formation_config=None,
                  shot_config=None, shot_calibration=None, highlight_config=None):
    """Analyze a local uploaded video and return a strict JSON-compatible dict.

    Each call uses fresh YOLO/ByteTrack state, never reads or writes old stubs,
    and writes output_video.avi and analysis.json inside a unique run directory.
    Core failures raise AnalysisError with a logged traceback. Optional highlights
    use the original upload by default; export failures are returned as diagnostics.
    highlight_config accepts a HighlightConfig instance or a configuration dict.
    """
    analysis_id = uuid4().hex
    run_directory = None
    stage = "validate input"
    try:
        logger.info("Starting analysis %s: %s", analysis_id, input_video_path)
        if not MODEL_PATH.is_file():
            raise FileNotFoundError(f"YOLO model is missing: {MODEL_PATH}")
        frames, metadata = read_video(input_video_path, return_metadata=True)
        run_directory = Path(output_directory).expanduser().resolve() / analysis_id
        run_directory.mkdir(parents=True, exist_ok=False)
        fps = metadata["fps"]
        logger.info("Decoded %d frames at %.6g FPS", len(frames), fps)

        stage = "detect and track"
        tracker = Tracker(str(MODEL_PATH), frame_rate=fps)
        tracks = tracker.get_object_tracks(frames, read_from_stub=False, stub_path=None)
        warnings = [
            "Speed and distance use the original fixed pitch calibration, which must "
            "be recalibrated for a different camera view. Values are estimates.",
        ]
        if not any(tracks["ball"]):
            warnings.append("No ball was detected; possession is unknown.")
        # Interpolate before position/transform calculation so ball metadata survives.
        observed_ball_frames = [bool(frame.get(1)) for frame in tracks["ball"]]
        tracks["ball"] = tracker.interpolate_ball_positions(tracks["ball"])
        for frame_index, ball_frame in enumerate(tracks["ball"]):
            if 1 in ball_frame:
                ball_frame[1]["is_observed"] = observed_ball_frames[frame_index]
        tracker.add_position_to_tracks(tracks)

        stage = "camera movement and perspective"
        camera = CameraMovementEstimator(frames[0])
        movement = camera.get_camera_movement(frames, read_from_stub=False, stub_path=None)
        camera.add_adjust_positions_to_tracks(tracks, movement)
        view_transformer = ViewTransformer()
        view_transformer.add_transformed_position_to_tracks(tracks)
        speed = SpeedAndDistanceEstimator(frame_rate=fps)
        speed.add_speed_and_distance_to_tracks(tracks)

        stage = "teams and possession"
        logger.info("Assigning teams and possession")
        teams = _assign_teams(frames, tracks, warnings)
        possession = []
        ball_assigner = PlayerBallAssigner()
        for frame_num, players in enumerate(tracks["players"]):
            ball = tracks["ball"][frame_num].get(1)
            for player in players.values():
                player["possession_evaluated"] = bool(ball and ball["is_observed"])
            player_id = ball_assigner.assign_ball_to_player(players, ball["bbox"]) if ball else -1
            if player_id != -1:
                players[player_id]["has_ball"] = True
                possession.append(int(players[player_id].get("team", 0)))
            else:
                # Preserve carry-forward possession; leading unknown frames are 0.
                possession.append(possession[-1] if possession else 0)

        stage = "annotated video"
        logger.info("Rendering annotations")
        output_frames = tracker.draw_annotations(frames, tracks, np.asarray(possession))
        del frames
        output_frames = camera.draw_camera_movement(output_frames, movement)
        speed.draw_speed_and_distance(output_frames, tracks)
        video_path = run_directory / "output_video.avi"
        save_video(output_frames, video_path, fps=fps)
        del output_frames

        stage = "analytics and results"
        logger.info("Building statistics, heatmaps, pass/shot hypotheses and tactics")
        result = build_results(analysis_id, metadata, tracks, movement, teams.team_colors,
                               possession, run_directory, warnings,
                               pitch_vertices=view_transformer.target_vertices, pass_config=pass_config,
                               formation_config=formation_config, shot_config=shot_config,
                               shot_calibration=shot_calibration)
        result["created_at"] = datetime.now(timezone.utc).isoformat()
        result.update(highlights=[], highlight_generation={"status": "not_generated"})
        json_path = run_directory / "analysis.json"
        temporary_path = run_directory / "analysis.json.tmp"
        # Save the complete main analysis before optional encoders consume disk space.
        temporary_path.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
        temporary_path.replace(json_path)
        # Optional exports cannot invalidate the completed CV/analytics pipeline.
        try:
            from .highlights import generate_highlights
            highlight_result = generate_highlights(
                result.get("events", []), input_video_path, run_directory,
                config=highlight_config, annotated_video_path=video_path, video_metadata=metadata)
            json.dumps(highlight_result, allow_nan=False)
            result.update(highlight_result)
        except Exception:
            logger.exception("Optional highlight stage failed; preserving analysis")
            result.update(highlights=[], highlight_generation={
                "status": "failed", "warnings": ["Highlight generation unavailable; see the local analysis log."]})
        try:
            temporary_path.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
            temporary_path.replace(json_path)
        except Exception:
            logger.exception("Could not persist highlight metadata; the original analysis JSON is preserved")
            result["highlight_generation"].setdefault("warnings", []).append(
                "Updated highlight metadata could not be saved; analysis.json retains the main analysis.")
        for warning in warnings:
            logger.warning(warning)
        logger.info("Analysis %s complete: %s", analysis_id, video_path)
        return result
    except Exception as exc:
        logger.exception("Analysis %s failed during %s", analysis_id, stage)
        if run_directory is not None and run_directory.is_dir():
            try:
                (run_directory / "failure.json").write_text(json.dumps({
                    "analysis_id": analysis_id, "status": "failed", "stage": stage,
                    "error": str(exc),
                }), encoding="utf-8")
            except OSError:
                logger.exception("Could not write failure metadata")
        raise AnalysisError(f"Analysis {analysis_id} failed during {stage}: {exc}") from exc






