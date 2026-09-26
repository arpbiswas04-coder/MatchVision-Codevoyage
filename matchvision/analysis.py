"""Orchestrate the existing football analysis components for one isolated run."""
import json
import traceback
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4, UUID
from .progress import report_progress

import numpy as np

from util import save_video
from util.video_source import VideoFrames
from .json_io import write_json
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


def _assign_teams(frames, tracks, warnings, progress_callback=None):
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
    for index, (frame, players) in enumerate(zip(frames, tracks["players"])):
        if progress_callback and index % 30 == 0:
            progress_callback(index, len(frames))
        for player_id, player in players.items():
            try:
                team = assigner.get_player_team(frame, player["bbox"], player_id)
            except ValueError:
                continue
            player.update(team=team, team_color=assigner.team_colors[team])
    return assigner


def analyze_match(input_video_path, output_directory, *, pass_config=None, formation_config=None,
                  shot_config=None, shot_calibration=None, highlight_config=None,
                  analysis_id=None, progress_callback=None):
    """Analyze a local uploaded video and return a strict JSON-compatible dict.

    Each call uses fresh YOLO/ByteTrack state, never reads or writes old stubs,
    and writes output_video.avi and analysis.json inside a unique run directory.
    Core failures raise AnalysisError with a logged traceback. Optional highlights
    use the original upload by default; export failures are returned as diagnostics.
    highlight_config accepts a HighlightConfig instance or a configuration dict.
    """
    if analysis_id is None:
        analysis_id = uuid4().hex
    elif not isinstance(analysis_id, str) or UUID(analysis_id).hex != analysis_id:
        raise ValueError("analysis_id must be a canonical UUID hex string")
    frames = None
    run_directory = None
    run_created = False
    stage = "validate input"

    def notify(percent, label):
        nonlocal stage
        stage = label
        logger.info("Analysis %s: %s (%s%%)", analysis_id, label, percent)
        report_progress(progress_callback, percent, label)
    try:
        notify(5, "Preparing video")
        logger.info("Starting analysis %s: %s", analysis_id, input_video_path)
        if not MODEL_PATH.is_file():
            raise FileNotFoundError(f"YOLO model is missing: {MODEL_PATH}")
        frames = VideoFrames(input_video_path)
        metadata = frames.metadata
        run_directory = Path(output_directory).expanduser().resolve() / analysis_id
        run_directory.mkdir(parents=True, exist_ok=False)
        run_created = True
        fps = metadata["fps"]
        logger.info("Source reports %d frames at %.6g FPS", len(frames), fps)

        stage = "detect and track"
        notify(8, "Detecting and tracking players")
        tracker = Tracker(str(MODEL_PATH), frame_rate=fps)
        tracks = tracker.get_object_tracks(
            frames, read_from_stub=False, stub_path=None,
            progress_callback=lambda done, total: notify(
                min(40, 8 + int(32 * done / max(1, total))),
                f"Detecting and tracking players: {done}/{total} frames"))
        tracker.release_model()
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
        notify(42, "Camera compensation and movement estimates")
        camera = CameraMovementEstimator(frames[0])
        movement = camera.get_camera_movement(
            frames, read_from_stub=False, stub_path=None,
            progress_callback=lambda done, total: notify(
                42 + int(10 * done / max(1, total)), f"Camera compensation: {done}/{total} frames"))
        camera.add_adjust_positions_to_tracks(tracks, movement)
        view_transformer = ViewTransformer()
        view_transformer.add_transformed_position_to_tracks(tracks)
        speed = SpeedAndDistanceEstimator(frame_rate=fps)
        speed.add_speed_and_distance_to_tracks(tracks)

        stage = "teams and possession"
        notify(55, "Assigning teams")
        logger.info("Assigning teams and possession")
        teams = _assign_teams(frames, tracks, warnings,
            progress_callback=lambda done, total: notify(
                55 + int(4 * done / max(1, total)), f"Assigning teams: {done}/{total} frames"))
        notify(60, "Calculating possession")
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

        notify(65, "Generating annotated video")
        video_path = run_directory / "output_video.avi"

        def annotated_frames():
            rendered = 0
            for index, frame in enumerate(tracker.iter_annotations(frames, tracks, np.asarray(possession))):
                frame = camera.draw_camera_movement([frame], [movement[index]])[0]
                speed.draw_speed_and_distance([frame], {key: [rows[index]] for key, rows in tracks.items()})
                rendered += 1
                if index % 30 == 0:
                    notify(65 + int(9 * index / len(frames)), f"Generating annotated video: {index}/{len(frames)} frames")
                yield frame
            if rendered != len(tracks["players"]):
                raise OSError("Annotated pass decoded a different frame count from the tracking pass")

        save_video(annotated_frames(), video_path, fps=fps)

        stage = "analytics and results"
        notify(75, "Calculating player and team statistics")
        logger.info("Building statistics, heatmaps, pass/shot hypotheses and tactics")
        result = build_results(analysis_id, metadata, tracks, movement, teams.team_colors,
                               possession, run_directory, warnings,
                               pitch_vertices=view_transformer.target_vertices, pass_config=pass_config,
                               formation_config=formation_config, shot_config=shot_config,
                               shot_calibration=shot_calibration, progress_callback=notify)
        del tracks, movement, possession
        result["tracking"] = getattr(tracker, "identity_diagnostics", {})
        result["created_at"] = datetime.now(timezone.utc).isoformat()
        result.update(highlights=[], highlight_generation={"status": "not_generated"})
        json_path = run_directory / "analysis.json"

        notify(89, 'Saving analysis results')
        # Save the complete main analysis before optional encoders consume disk space.
        write_json(json_path, result)
        notify(90, "Generating highlights")
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
        notify(98, 'Finalising analysis results')
        try:
            write_json(json_path, result)
        except Exception:
            logger.exception("Could not persist highlight metadata; the original analysis JSON is preserved")
            result["highlight_generation"].setdefault("warnings", []).append(
                "Updated highlight metadata could not be saved; analysis.json retains the main analysis.")
        notify(100, "Analysis engine complete")
        for warning in warnings:
            logger.warning(warning)
        logger.info("Analysis %s complete: %s", analysis_id, video_path)
        return result
    except Exception as exc:
        logger.exception("Analysis %s failed during %s", analysis_id, stage)
        if run_created and run_directory is not None and run_directory.is_dir():
            try:
                (run_directory / "failure.json").write_text(json.dumps({
                    "analysis_id": analysis_id, "status": "failed", "stage": stage,
                    "error": str(exc), "exception_type": type(exc).__name__, "traceback": traceback.format_exc(),
                }), encoding="utf-8")
            except OSError:
                logger.exception("Could not write failure metadata")
        raise AnalysisError(f"Analysis {analysis_id} failed during {stage}: {exc}") from exc
    finally:
        if frames is not None:
            frames.close()

