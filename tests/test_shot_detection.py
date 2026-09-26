"""Synthetic shot-detection cases for manual execution only; no video/model fixtures."""
from copy import deepcopy
import json
import math
import unittest

from matchvision.analytics import ShotDetectionConfig, ShotEvent, build_analytics, detect_shots
from matchvision.analytics.events import merge_event_detections

PITCH = [[0, 0], [105, 0], [105, 68], [0, 68]]


def calibration(frame_count):
    # Explicit synthetic coordinate system. This is not calibration for the supplied video.
    return {"validated_for_input": True, "coordinate_system": "transformed_pitch_meters",
            "source": "synthetic test fixture only", "periods": [{
                "start_frame": 0, "end_frame_exclusive": frame_count,
                "attacking_goals": {"1": {"center": [105, 34], "half_width_m": 3.66},
                                    "2": {"center": [0, 34], "half_width_m": 3.66}},
            }]}


def history(fps=25, speed=20, initial_x=85, team=1, direction=1, lateral_speed=0):
    config = ShotDetectionConfig()
    hold = config.thresholds(fps)["possession_observations"]
    flight = math.floor(config.trajectory_window_seconds * fps)
    players, balls = [], []
    for index in range(hold + flight):
        elapsed = max(0, index - hold + 1) / fps
        point = [initial_x + direction * speed * elapsed, 34 + lateral_speed * elapsed]
        players.append({7: {"team": team, "position_transformed": [initial_x, 34],
                            "possession_evaluated": True, "has_ball": index < hold}})
        balls.append({1: {"is_observed": True, "position_transformed": point}})
    return {"players": players, "ball": balls}, hold - 1


def run_detector(tracks, fps=25, **options):
    return detect_shots(tracks, fps, PITCH, calibration=calibration(len(tracks["players"])), **options)


class ShotDetectionTests(unittest.TestCase):
    def test_probable_shot_at_actual_fps_in_both_directions(self):
        for fps in (10, 25, 29.97, 60):
            for team, direction, start in ((1, 1, 85), (2, -1, 20)):
                with self.subTest(fps=fps, team=team):
                    tracks, release = history(fps, team=team, direction=direction, initial_x=start)
                    before = deepcopy(tracks)
                    result = run_detector(tracks, fps)
                    self.assertEqual(len(result["events"]), 1)
                    event = result["events"][0]
                    self.assertEqual(event["type"], "shot")
                    self.assertEqual(event["classification"], "probable_shot")
                    self.assertEqual((event["team"], event["player"]), (team, 7))
                    self.assertEqual(event["frame"], release)
                    self.assertAlmostEqual(event["timestamp"], release / fps)
                    self.assertEqual(event["position"], [start, 34])
                    self.assertGreater(event["confirmation_frame"], release)
                    self.assertGreaterEqual(event["confidence"], 0.80)
                    self.assertLessEqual(event["confidence"], 0.95)
                    self.assertAlmostEqual(event["evidence"]["net_speed_mps"], 20)
                    self.assertEqual(tracks, before)
                    json.dumps(result, allow_nan=False)

    def test_default_unvalidated_or_incompatible_calibration_skips_gracefully(self):
        tracks, _ = history()
        invalid = calibration(len(tracks["players"]))
        invalid["validated_for_input"] = False
        for value in (None, {}, invalid):
            result = detect_shots(tracks, 25, PITCH, calibration=value)
            self.assertEqual(result["events"], [])
            self.assertEqual(result["event_detection"]["status"], "skipped_calibration")
            self.assertTrue(result["event_detection"]["reasons"])
        result = detect_shots(tracks, 25, [[0, 0], [23.32, 0], [23.32, 68], [0, 68]],
                              calibration=calibration(len(tracks["players"])))
        self.assertEqual(result["event_detection"]["status"], "skipped_calibration")

    def test_overlapping_goal_periods_and_unknown_direction_are_not_guessed(self):
        tracks, _ = history()
        value = calibration(len(tracks["players"]))
        value["periods"].append(deepcopy(value["periods"][0]))
        self.assertEqual(detect_shots(tracks, 25, PITCH, calibration=value)["event_detection"]["status"], "skipped_calibration")
        value = calibration(len(tracks["players"]))
        del value["periods"][0]["attacking_goals"]["1"]
        result = detect_shots(tracks, 25, PITCH, calibration=value)
        self.assertEqual(result["events"], [])
        self.assertEqual(result["event_detection"]["rejection_evaluations"]["attacking_goal_unknown_for_team"], 1)

    def test_slow_away_far_and_wide_trajectories_are_rejected(self):
        for details in ({"speed": 4}, {"direction": -1}, {"initial_x": 50},
                        {"lateral_speed": 10}, {"lateral_speed": 30}):
            with self.subTest(details=details):
                tracks, _ = history(**details)
                self.assertEqual(run_detector(tracks)["events"], [])

    def test_implausible_jump_and_high_confidence_threshold_are_rejected(self):
        tracks, _ = history(speed=80)
        self.assertEqual(run_detector(tracks)["events"], [])
        tracks, _ = history()
        self.assertEqual(run_detector(tracks, config=ShotDetectionConfig(confidence_threshold=0.99))["events"], [])

    def test_missing_observed_ball_owner_and_coordinates_do_not_fabricate_shots(self):
        for mode in ("interpolated", "missing_position", "no_owner", "no_evaluation", "ambiguous"):
            tracks, _ = history()
            for players, balls in zip(tracks["players"], tracks["ball"]):
                if mode == "interpolated":
                    balls[1]["is_observed"] = False
                elif mode == "missing_position":
                    balls[1]["position_transformed"] = None
                elif mode == "no_owner":
                    players[7]["has_ball"] = False
                elif mode == "no_evaluation":
                    players[7]["possession_evaluated"] = False
                else:
                    players[8] = deepcopy(players[7])
            with self.subTest(mode=mode):
                self.assertEqual(run_detector(tracks)["events"], [])

    def test_confirmed_pass_same_release_suppresses_shot(self):
        tracks, release = history()
        result = run_detector(tracks, pass_events=[{
            "type": "pass", "team": 1, "player_from": 7, "player_to": 10,
            "release_frame": release, "frame": len(tracks["players"]) - 1,
        }])
        self.assertEqual(result["events"], [])
        self.assertEqual(result["event_detection"]["rejection_evaluations"]["confirmed_pass_same_release"], 1)

    def test_long_observation_gap_and_period_boundary_break_trajectory(self):
        tracks, release = history()
        for index in range(release + 1, release + 5):
            tracks["ball"][index] = {}
        self.assertEqual(run_detector(tracks)["events"], [])
        tracks, release = history()
        value = calibration(len(tracks["players"]))
        second = deepcopy(value["periods"][0])
        value["periods"][0]["end_frame_exclusive"] = release + 2
        second["start_frame"] = release + 2
        value["periods"].append(second)
        self.assertEqual(detect_shots(tracks, 25, PITCH, calibration=value)["events"], [])

    def test_release_consumption_and_global_cooldown_prevent_duplicates(self):
        one, _ = history()
        gap = math.ceil(2.0 * 25)
        tracks = {"players": one["players"] + deepcopy(one["players"]) + [{} for _ in range(gap)] + deepcopy(one["players"]),
                  "ball": one["ball"] + deepcopy(one["ball"]) + [{} for _ in range(gap)] + deepcopy(one["ball"])}
        result = run_detector(tracks)
        self.assertEqual(len(result["events"]), 2)
        self.assertEqual(result["event_detection"]["rejection_evaluations"]["cooldown"], 1)
        self.assertGreaterEqual(result["events"][1]["timestamp"] - result["events"][0]["timestamp"], 1.50)

    def test_short_clip_does_not_flush_unconfirmed_candidate(self):
        tracks, release = history()
        tracks = {kind: frames[:release + 2] for kind, frames in tracks.items()}
        self.assertEqual(run_detector(tracks)["events"], [])

    def test_timeline_sorting_replacement_and_legacy_pass_metadata(self):
        shot = ShotEvent.at_frame("shot", 3, 25, player=7, team=1, position=(85, 34), confidence=0.85).to_dict()
        passes = {"events": [{"type": "pass", "frame": 8}], "event_detection": {"status": "completed", "detected_passes": 1}}
        shots = {"events": [shot], "event_detection": {"status": "completed", "detected_shots": 1}, "calibration": None}
        result = merge_event_detections(passes, shots, [{"type": "shot", "frame": 1}, {"type": "pass", "frame": 2}])
        self.assertEqual([event["frame"] for event in result["events"]], [3, 8])
        self.assertEqual(result["event_detection"]["detected_passes"], 1)
        self.assertEqual(result["event_detection"]["shots"]["detected_shots"], 1)

    def test_pipeline_analytics_keeps_shots_out_of_passing_network(self):
        tracks, _ = history()
        result = build_analytics(tracks, 25, [1] * len(tracks["players"]), {}, PITCH,
                                 shot_calibration=calibration(len(tracks["players"])))
        self.assertEqual([event["type"] for event in result["events"]], ["shot"])
        self.assertEqual(result["tactics"]["teams"]["1"]["passing_network"]["edges"], [])
        self.assertEqual(result["event_detection"]["shots"]["status"], "completed")
        json.dumps(result, allow_nan=False)

    def test_event_and_timing_validation(self):
        with self.assertRaises(ValueError):
            ShotEvent.at_frame("shot", 1, 25, team=1, player=7, position=(float("nan"), 1), confidence=0.8)
        with self.assertRaises(ValueError):
            ShotDetectionConfig(confidence_threshold=1.1)
        with self.assertRaises(ValueError):
            detect_shots({}, 0)


if __name__ == "__main__":
    unittest.main()
