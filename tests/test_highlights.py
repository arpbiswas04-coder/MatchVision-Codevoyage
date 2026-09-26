"""Manual-run regression coverage for optional highlights. Not executed during implementation."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from matchvision.highlights import HighlightConfig, generate_highlights, plan_highlights
from matchvision.highlights.paths import resolve_highlight_asset
from matchvision.highlights.video import export_clip


def shot(timestamp, confidence=0.95):
    return {"type": "shot", "timestamp": timestamp, "confidence": confidence}


class HighlightTests(unittest.TestCase):
    def test_clamps_and_merges_nearby_actions(self):
        plan = plan_highlights([shot(2), shot(14), shot(29)], 30)
        self.assertEqual([(w["start"], w["end"]) for w in plan["windows"]], [(0, 20), (24, 30)])
        self.assertEqual(len(plan["windows"][0]["events"]), 2)

    def test_filters_passes_noise_and_out_of_video_events(self):
        events = [{"type": "pass", "timestamp": 5, "confidence": 1},
                  shot(6, 0.4), shot(float("nan")), shot(30), None, shot(10)]
        plan = plan_highlights(events, 30)
        self.assertEqual(plan["eligible_events"], 1)
        self.assertEqual(plan["windows"][0]["timestamp"], 10)

    def test_limit_after_merging_and_sanitize_event_fields(self):
        events = [dict(shot(10), video_path="C:/private/video.mp4"),
                  shot(11), shot(40, 0.99)]
        plan = plan_highlights(events, 60, HighlightConfig(max_clips=1))
        self.assertEqual(plan["omitted_windows"], 1)
        self.assertEqual(plan["windows"][0]["timestamp"], 40)
        all_windows = plan_highlights(events, 60)["windows"]
        self.assertNotIn("video_path", all_windows[0]["events"][0])

    def test_no_events_does_not_probe_or_export(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("matchvision.highlights.service.probe_source") as probe:
                result = generate_highlights([], "missing.mp4", directory)
            probe.assert_not_called()
            self.assertEqual(result["highlight_generation"]["status"], "no_eligible_events")
            self.assertTrue((Path(directory) / "highlights/highlights.json").is_file())

    def test_export_failure_is_contained_and_original_source_is_used(self):
        info = dict(fps=30, frame_count=1800, width=640, height=360,
                    duration_seconds=60, duration_source="test")
        with tempfile.TemporaryDirectory() as directory:
            with patch("matchvision.highlights.service.probe_source", return_value=info), patch(
                    "matchvision.highlights.service.export_clip", side_effect=OSError("private path")) as export:
                result = generate_highlights([shot(20)], "original.mp4", directory,
                                             annotated_video_path="annotated.avi")
            self.assertEqual(export.call_args.args[0], "original.mp4")
            self.assertEqual(result["highlights"], [])
            self.assertEqual(result["highlight_generation"]["status"], "failed")
            self.assertNotIn("private path", str(result))

    def test_missing_ffmpeg_uses_opencv(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "highlights").mkdir()
            def encode(source, target, window, info, timeout):
                target.write_bytes(b"mock clip")
                return dict(start=5, end=16, backend="opencv", audio_mode="video_only")
            with patch("matchvision.highlights.video.shutil.which", return_value=None), patch(
                    "matchvision.highlights.video._opencv", side_effect=encode), patch(
                    "matchvision.highlights.video._validate_clip"):
                result = export_clip("original.mp4", directory, "a" * 32,
                                     {"start": 5, "end": 16}, {}, HighlightConfig())
            self.assertTrue(result["fallback_used"])
            self.assertEqual(result["video_path"], "highlights/clip_" + "a" * 32 + ".avi")
            self.assertTrue(resolve_highlight_asset(directory, result["video_path"]).is_file())

    def test_asset_resolution_rejects_arbitrary_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            for path in ("../video.mp4", "C:/private.mp4", "highlights/other.mp4"):
                with self.assertRaises(ValueError):
                    resolve_highlight_asset(directory, path)

    def test_invalid_settings_are_optional_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            result = generate_highlights([shot(10)], "original.mp4", directory,
                                         config={"before_seconds": -5})
            self.assertEqual(result["highlight_generation"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
