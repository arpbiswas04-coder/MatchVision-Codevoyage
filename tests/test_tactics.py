"""Synthetic tactical analytics cases for manual execution; no video fixtures."""
from copy import deepcopy
import json
import unittest

from matchvision.analytics import FormationConfig, build_tactics

FULL_PITCH = [[0, 0], [105, 0], [105, 68], [0, 68]]
UNKNOWN = "Unknown / insufficient tracking data"


def player(team, position):
    return {"team": team, "position_transformed": position}


def shape_frames(shape, count=10, reverse=False):
    frame = {1: player(1, [100 if reverse else 5, 34])}
    next_id = 2
    rows = [25, 50, 75] if len(shape) == 3 else [25, 42, 59, 76]
    for row, size in zip(rows, shape):
        for slot in range(size):
            frame[next_id] = player(1, [105 - row if reverse else row, 68 * (slot + 1) / (size + 1)])
            next_id += 1
    return [deepcopy(frame) for _ in range(count)]


class TacticsTests(unittest.TestCase):
    def test_average_positions_geometry_and_missing_frames(self):
        tracks = {"players": [
            {1: player(1, [0, 0]), 2: player(1, [6, 8]), 3: player(2, None)},
            {1: player(1, [2, 0]), 2: player(1, [8, 8]), 3: player(2, [3, 4])}, {},
        ]}
        before = deepcopy(tracks)
        result = build_tactics(tracks, [], 2, FULL_PITCH)
        self.assertEqual(result["players"][0]["average_position"], [1, 0])
        self.assertEqual(result["players"][0]["positioned_time_seconds"], 1)
        team = result["teams"]["1"]
        first = team["timeline"][0]
        self.assertEqual(first["centroid"], [3, 4])
        self.assertEqual(first["width_m"], 8)  # lateral y, not x
        self.assertEqual(first["length_m"], 6)
        self.assertEqual(first["compactness_mean_radius_m"], 5)
        self.assertEqual(team["timeline"][1]["timestamp"], 0.5)
        self.assertIsNone(team["timeline"][2]["centroid"])
        self.assertIsNone(team["timeline"][2]["width_m"])
        self.assertEqual(team["summary"]["average_centroid"], [4, 4])
        self.assertEqual(team["summary"]["spread_frames"], 2)
        self.assertEqual(result["teams"]["2"]["timeline"][1]["centroid"], [3, 4])
        self.assertIsNone(result["teams"]["2"]["timeline"][1]["compactness_mean_radius_m"])
        self.assertEqual(tracks, before)
        json.dumps(result, allow_nan=False)

    def test_network_is_directed_and_counts_only_valid_detected_events(self):
        tracks = {"players": [{1: player(1, [1, 1]), 2: player(1, None), 3: player(2, [3, 3])}] * 3}
        def event(frame, source, target, team=1):
            return {"type": "pass", "frame": frame, "team": team, "player_from": source, "player_to": target}
        events = [event(0, 1, 2), event(0, 1, 2), event(1, 1, 2), event(1, 2, 1),
                  event(0, 1, 1), event(0, 1, 3), event(0, 1, 99), event(4, 1, 2)]
        result = build_tactics(tracks, events, 25, FULL_PITCH, event_detection={"status": "completed"})
        network = result["teams"]["1"]["passing_network"]
        self.assertEqual(network["edges"], [
            {"source_player": 1, "target_player": 2, "number_of_passes": 2},
            {"source_player": 2, "target_player": 1, "number_of_passes": 1},
        ])
        self.assertEqual(network["total_passes"], 3)
        self.assertFalse(network["nodes"][1]["position_available"])
        self.assertIsNone(network["nodes"][1]["average_position"])
        self.assertEqual(result["quality"]["duplicate_pass_events_ignored"], 1)
        self.assertEqual(result["quality"]["excluded_pass_events"], 4)
        self.assertEqual(network["pass_detection_status"], "completed")

    def test_unknown_and_conflicting_teams_do_not_leak_into_team_metrics(self):
        tracks = {"players": [{1: player(1, [1, 1]), 2: player(None, [3, 3])},
                               {1: player(2, [2, 2])}]}
        result = build_tactics(tracks, [], 25, FULL_PITCH)
        self.assertEqual(result["players"][0]["average_position"], [1.5, 1.5])
        self.assertIsNone(result["players"][0]["team_id"])
        self.assertEqual(result["quality"]["conflicting_team_track_ids"], [1])
        self.assertEqual(result["teams"]["1"]["passing_network"]["nodes"], [])
        self.assertIsNone(result["teams"]["2"]["timeline"][1]["centroid"])

    def test_invalid_positions_stay_unavailable_and_json_keys_work(self):
        points = [None, [float("nan"), 1], [1, float("inf")], [106, 1], [1], "bad"]
        tracks = {"players": [{str(index): player(1, point) for index, point in enumerate(points)}]}
        result = build_tactics(tracks, [], 25, FULL_PITCH)
        self.assertTrue(all(item["average_position"] is None for item in result["players"]))
        self.assertIsNone(result["teams"]["1"]["summary"]["average_width_m"])
        json.dumps(result, allow_nan=False)

    def test_supported_formations_are_explainable_and_orientation_aware(self):
        for shape in ((4, 4, 2), (4, 3, 3), (4, 2, 3, 1)):
            for reverse in (False, True):
                with self.subTest(shape=shape, reverse=reverse):
                    result = build_tactics({"players": shape_frames(shape, reverse=reverse)}, [], 1, FULL_PITCH)
                    formation = result["teams"]["1"]["formation"]
                    self.assertEqual(formation["label"], "-".join(map(str, shape)))
                    evidence = formation["windows"][0]
                    self.assertEqual(evidence["goalkeeper_candidate_id"], 1)
                    self.assertEqual([len(line["player_ids"]) for line in evidence["lines"]], list(shape))
                    self.assertEqual(evidence["joint_coverage"], 1)
                    self.assertEqual(evidence["longitudinal_direction"], "decreasing_x" if reverse else "increasing_x")

    def test_partial_region_short_duration_and_fragmentation_return_unknown(self):
        partial = [[0, 0], [23.32, 0], [23.32, 68], [0, 68]]
        tracks = {"players": shape_frames((4, 4, 2))}
        result = build_tactics(tracks, [], 1, partial)
        self.assertEqual(result["teams"]["1"]["formation"]["label"], UNKNOWN)
        self.assertIn("too small", result["teams"]["1"]["formation"]["windows"][0]["reasons"][0])
        result = build_tactics({"players": shape_frames((4, 4, 2), count=9)}, [], 1, FULL_PITCH)
        self.assertEqual(result["teams"]["1"]["formation"]["label"], UNKNOWN)
        for frame in tracks["players"][5:]:
            frame[99] = frame.pop(2)
        result = build_tactics(tracks, [], 1, FULL_PITCH)
        self.assertEqual(result["teams"]["1"]["formation"]["label"], UNKNOWN)

    def test_no_goalkeeper_guess_or_nearest_template_guess(self):
        frames = shape_frames((4, 4, 2))
        for frame in frames:
            frame[11]["position_transformed"][0] = 100
        result = build_tactics({"players": frames}, [], 1, FULL_PITCH)
        self.assertEqual(result["teams"]["1"]["formation"]["label"], UNKNOWN)
        result = build_tactics({"players": shape_frames((3, 3, 4))}, [], 1, FULL_PITCH)
        self.assertEqual(result["teams"]["1"]["formation"]["label"], UNKNOWN)

    def test_conflicting_windows_are_not_collapsed_into_one_formation(self):
        frames = shape_frames((4, 4, 2)) + shape_frames((4, 3, 3))
        result = build_tactics({"players": frames}, [], 1, FULL_PITCH,
                              formation_config=FormationConfig(window_seconds=10))
        formation = result["teams"]["1"]["formation"]
        self.assertEqual([window["label"] for window in formation["windows"]], ["4-4-2", "4-3-3"])
        self.assertEqual(formation["label"], UNKNOWN)

    def test_timing_uses_fps_and_empty_data_is_not_fabricated(self):
        frames = shape_frames((4, 4, 2), count=100)
        result = build_tactics({"players": frames}, [], 10, FULL_PITCH)
        self.assertEqual(result["teams"]["1"]["formation"]["label"], "4-4-2")
        self.assertEqual(result["teams"]["1"]["formation"]["window_frames"], 300)
        empty = build_tactics({}, [], 25, FULL_PITCH)
        self.assertEqual(empty["players"], [])
        self.assertEqual(empty["teams"]["1"]["passing_network"]["edges"], [])
        self.assertIsNone(empty["teams"]["1"]["summary"]["average_centroid"])
        self.assertEqual(empty["teams"]["1"]["formation"]["label"], UNKNOWN)
        with self.assertRaises(ValueError):
            build_tactics({}, [], 0, FULL_PITCH)


if __name__ == "__main__":
    unittest.main()
