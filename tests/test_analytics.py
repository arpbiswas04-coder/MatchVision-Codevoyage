"""Deterministic analytics checks independent of model predictions."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from matchvision.analytics import MatchEvent, build_analytics, build_heatmaps, summarize_statistics

PITCH = [[0, 0], [10, 0], [10, 10], [0, 10]]


def sample_tracks():
    return {
        "players": [
            {7: {"team": 1, "speed": 0, "distance": 0, "position_transformed": [0, 0],
                 "possession_evaluated": True}},
            {},
            {7: {"team": 1, "speed": 10, "distance": 5, "position_transformed": [1, 1],
                 "possession_evaluated": True, "has_ball": True},
             8: {"team": 1, "speed": 20, "distance": 3, "position_transformed": [10, 10],
                 "possession_evaluated": False, "has_ball": True},
             9: {"team": 2, "position_transformed": None}},
            {7: {"team": 1, "speed": 20, "distance": 5, "position_transformed": None,
                 "possession_evaluated": False, "has_ball": True}},
        ],
        "ball": [
            {1: {"position_transformed": [0, 0], "is_observed": True}},
            {1: {"position_transformed": [5, 5], "is_observed": False}},
            {1: {"position_transformed": None, "is_observed": True}},
            {1: {"position_transformed": [10, 10], "is_observed": True}},
        ],
        "referees": [{}, {}, {}, {}],
    }


class AnalyticsTests(unittest.TestCase):
    def test_statistics_account_for_gaps_and_measurement_coverage(self):
        result = summarize_statistics(sample_tracks()["players"], 2, [0, 1, 1, 2], {1: np.array([1, 2, 3])})
        json.dumps(result, allow_nan=False)
        players = {p["player_id"]: p for p in result["players"]}
        player = players[7]
        self.assertEqual(player["observed_frames"], 3)
        self.assertEqual(player["tracked_time_seconds"], 1.5)
        self.assertEqual(player["average_speed_kmh"], 10)
        self.assertEqual(player["max_speed_kmh"], 20)
        self.assertEqual(player["distance_m"], 5)  # cumulative values must not be summed
        self.assertEqual(player["possession_time_seconds"], 0.5)
        self.assertEqual(player["possession_evaluated_frames"], 2)
        self.assertIsNone(players[8]["possession_time_seconds"])
        self.assertIsNone(players[9]["distance_m"])
        self.assertIsNone(players[9]["average_speed_kmh"])
        team = result["teams"][0]
        self.assertEqual(team["total_distance_m"], 8)
        self.assertEqual(team["average_player_speed_kmh"], 15)
        self.assertEqual(team["tracked_player_count"], 2)
        self.assertEqual(team["distance_measured_players"], 2)
        self.assertAlmostEqual(team["possession_percentage"], 200 / 3)
        self.assertIsNone(result["teams"][1]["total_distance_m"])

    def test_invalid_measurements_stay_unknown_but_measured_zero_is_zero(self):
        frames = [{1: {"speed": np.nan, "distance": np.inf},
                   2: {"speed": -1, "distance": -3},
                   3: {"speed": 0, "distance": 0, "possession_evaluated": True}}]
        result = summarize_statistics(frames, 25, [0], {})
        self.assertIsNone(result["players"][0]["max_speed_kmh"])
        self.assertIsNone(result["players"][1]["distance_m"])
        self.assertEqual(result["players"][2]["distance_m"], 0)
        self.assertEqual(result["players"][2]["possession_time_seconds"], 0)
        self.assertIsNone(result["possession"]["team_percentages"]["1"])
        json.dumps(result, allow_nan=False)

    def test_conflicting_team_assignments_are_not_guessed(self):
        result = summarize_statistics([{4: {"team": 1}}, {4: {"team": 2}}], 25, [0, 0], {})
        self.assertIsNone(result["players"][0]["team_id"])
        self.assertEqual(result["teams"][0]["tracked_player_count"], 0)

    def test_heatmap_counts_boundaries_and_pngs(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = build_heatmaps(sample_tracks(), 2, PITCH, tmp, bins=(2, 2))
            self.assertEqual(result["players"]["7"]["sample_count"], 2)
            self.assertEqual(result["teams"]["1"]["counts"], [[2, 0], [0, 1]])
            self.assertEqual(result["teams"]["1"]["occupancy_seconds"], [[1, 0], [0, 0.5]])
            self.assertEqual(result["ball"]["counts"], [[1, 0], [0, 1]])
            self.assertEqual(result["ball"]["sample_count"], 2)
            self.assertEqual(result["excluded_samples"]["ball_unobserved_or_unknown_provenance"], 1)
            self.assertFalse(result["players"]["9"]["available"])
            self.assertIsNone(result["teams"]["2"]["image_path"])
            for path in Path(tmp).glob("heatmaps/*.png"):
                image = cv2.imread(str(path))
                self.assertIsNotNone(image)
                self.assertGreater(image.std(), 0)
            self.assertEqual(len(list(Path(tmp).glob("heatmaps/*.png"))), 4)
            json.dumps(result, allow_nan=False)

    def test_missing_malformed_and_outside_positions_are_excluded(self):
        tracks = {"players": [{i: {"position_transformed": point} for i, point in enumerate(
            [None, [np.nan, 1], [1, np.inf], [11, 1], [1], "invalid", [-1, 1]])}],
            "ball": [{1: {"position_transformed": [1, 1]}}]}
        result = build_heatmaps(tracks, 25, PITCH)
        self.assertTrue(all(not player["available"] for player in result["players"].values()))
        self.assertFalse(result["ball"]["available"])
        self.assertEqual(result["excluded_samples"]["player_positions_missing_or_outside_region"], 7)
        self.assertEqual(result["excluded_samples"]["ball_unobserved_or_unknown_provenance"], 1)

    def test_failed_optional_image_keeps_numeric_data(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "matchvision.analytics.heatmaps.cv2.imwrite", return_value=False
        ), self.assertLogs("matchvision.analytics.heatmaps", level="WARNING"):
            result = build_heatmaps(sample_tracks(), 2, PITCH, tmp)
        self.assertEqual(result["ball"]["sample_count"], 2)
        self.assertIsNone(result["ball"]["image_path"])
        self.assertTrue(result["warnings"])

    def test_empty_analytics_does_not_fabricate_events_or_measurements(self):
        result = build_analytics({}, 25, [], {}, PITCH)
        self.assertEqual(result["players"], [])
        self.assertEqual(result["events"], [])
        self.assertEqual(result["event_detection"]["status"], "insufficient_data")
        self.assertIsNone(result["teams"][0]["total_distance_m"])
        self.assertIsNone(result["teams"][0]["possession_percentage"])
        self.assertFalse(result["heatmaps"]["ball"]["available"])
        json.dumps(result, allow_nan=False)

    def test_event_serialization_and_validation(self):
        event = MatchEvent.at_frame("pass", np.int64(702), 30, team=1,
                                    player_from=7, player_to=10, confidence=0.82)
        self.assertEqual(json.loads(json.dumps(event.to_dict(), allow_nan=False)), {
            "type": "pass", "timestamp": 23.4, "frame": 702, "team": 1,
            "player_from": 7, "player_to": 10, "confidence": 0.82,
        })
        self.assertIsNone(MatchEvent.at_frame("shot", 25, 25).to_dict()["confidence"])
        for details in ({"confidence": 1.1}, {"confidence": np.nan}, {"team": 3}, {"player_from": -1}):
            with self.subTest(details=details), self.assertRaises(ValueError):
                MatchEvent.at_frame("pass", 2, 25, **details)
        with self.assertRaises(ValueError):
            MatchEvent.at_frame("pass", 2.5, 25)
        with self.assertRaises(ValueError):
            MatchEvent.at_frame("pass", 2, 0)


if __name__ == "__main__":
    unittest.main()

