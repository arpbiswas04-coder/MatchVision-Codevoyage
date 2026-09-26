import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from matchvision import AnalysisError, analyze_match
from matchvision.results import to_json_value
from speed_and_distance_estimator import SpeedAndDistanceEstimator
from trackers import Tracker
from util import read_video, save_video


class MatchVisionTests(unittest.TestCase):
    def test_video_roundtrip_uses_source_fps(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.avi"
            save_video([np.zeros((120, 160, 3), np.uint8)] * 3, path, fps=12.5)
            frames, meta = read_video(path, return_metadata=True)
            self.assertEqual(len(frames), 3)
            self.assertAlmostEqual(meta["fps"], 12.5)
            self.assertAlmostEqual(meta["duration_seconds"], 0.24)

    def test_speed_uses_fps_and_single_frame_does_not_divide_by_zero(self):
        tracks = {"players": [{1: {"position_transformed": [index, 0]}} for index in range(6)]}
        SpeedAndDistanceEstimator(frame_rate=25).add_speed_and_distance_to_tracks(tracks)
        self.assertAlmostEqual(tracks["players"][0][1]["speed"], 90)
        self.assertAlmostEqual(tracks["players"][0][1]["distance"], 5)
        SpeedAndDistanceEstimator(frame_rate=25).add_speed_and_distance_to_tracks(
            {"players": [{1: {"position_transformed": [0, 0]}}]})

    def test_ball_interpolation_and_no_detections(self):
        tracker = Tracker.__new__(Tracker)
        self.assertEqual(tracker.interpolate_ball_positions([{}, {}]), [{}, {}])
        interpolated = tracker.interpolate_ball_positions([{}, {1: {"bbox": [1, 2, 3, 4]}}, {}])
        self.assertEqual(interpolated[0][1]["bbox"], [1, 2, 3, 4])
        self.assertEqual(interpolated[-1][1]["bbox"], [1, 2, 3, 4])

    def test_strict_json_conversion(self):
        result = to_json_value({np.int64(3): np.array([1, np.nan]), "team": np.int64(2)})
        self.assertEqual(json.loads(json.dumps(result, allow_nan=False)), {"3": [1.0, None], "team": 2})

    def test_isolated_runs_with_no_detections_use_no_stubs(self):
        # Only detection is replaced; video I/O, camera, transformation and annotations are real.
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "uploaded clip.avi"
            save_video([np.zeros((120, 160, 3), np.uint8)] * 2, source, fps=12.5)
            with patch.object(Tracker, "__init__", return_value=None) as init, patch.object(
                Tracker, "get_object_tracks", side_effect=lambda *args, **kwargs: {
                    "players": [{}, {}], "ball": [{}, {}], "referees": [{}, {}]
                }
            ) as detection:
                first = analyze_match(source, Path(tmp) / "results")
                second = analyze_match(source, Path(tmp) / "results")
            self.assertNotEqual(first["analysis_id"], second["analysis_id"])
            self.assertEqual(init.call_args.kwargs["frame_rate"], 12.5)
            self.assertEqual(detection.call_args.kwargs, {"read_from_stub": False, "stub_path": None})
            self.assertEqual(first["possession"]["unknown_frames"], 2)
            self.assertEqual(first["players"], [])
            self.assertEqual(first["schema_version"], "2.3")
            self.assertEqual(first["match"]["fps"], 12.5)
            self.assertEqual(first["events"], [])
            self.assertEqual(first["event_detection"]["shots"]["status"], "skipped_calibration")
            self.assertEqual(first["tactics"]["players"], [])
            self.assertEqual(first["tactics"]["teams"]["1"]["formation"]["label"],
                             "Unknown / insufficient tracking data")
            self.assertFalse(first["heatmaps"]["ball"]["available"])
            self.assertIsNone(first["teams"][0]["possession_percentage"])
            self.assertEqual(first["output_video"], first["artifacts"]["annotated_video"])
            self.assertEqual(json.loads(Path(first["artifacts"]["analysis_json"]).read_text()), first)
            frames, meta = read_video(first["artifacts"]["annotated_video"], return_metadata=True)
            self.assertEqual(len(frames), 2)
            self.assertEqual(meta["fps"], 12.5)

    def test_missing_input_and_failed_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertLogs("matchvision.analysis", level="ERROR"), self.assertRaises(AnalysisError) as caught:
                analyze_match(Path(tmp) / "missing.mp4", tmp)
            self.assertIsInstance(caught.exception.__cause__, FileNotFoundError)
            source = Path(tmp) / "clip.avi"
            save_video([np.zeros((120, 160, 3), np.uint8)], source, fps=30)
            with patch("matchvision.analysis.Tracker", side_effect=RuntimeError("model failed")):
                with self.assertLogs("matchvision.analysis", level="ERROR"), self.assertRaises(AnalysisError):
                    analyze_match(source, Path(tmp) / "results")
            failure = next((Path(tmp) / "results").glob("*/failure.json"))
            self.assertEqual(json.loads(failure.read_text())["stage"], "detect and track")
            self.assertFalse((failure.parent / "analysis.json").exists())


if __name__ == "__main__":
    unittest.main()



