"""Manual-run regression cases for conservative pass inference; no video/model fixtures."""
from copy import deepcopy
import json
import math
import unittest

from matchvision.analytics import PassDetectionConfig, PassEvent, build_analytics, detect_passes

PITCH = [[0, 0], [10, 0], [10, 10], [0, 10]]


def history(owners, *, positions=True):
    tracks = {"players": [], "ball": []}
    for owner in owners:
        observed = owner != "missing"
        players = {}
        for player_id, team, point in ((7, 1, [0, 0]), (10, 1, [3, 4]), (20, 2, [8, 8])):
            players[player_id] = {
                "team": team, "position_transformed": point if positions else None,
                "possession_evaluated": observed,
                "has_ball": owner == player_id or (owner == "ambiguous" and player_id in (7, 10)),
            }
        tracks["players"].append(players)
        tracks["ball"].append({1: {"is_observed": observed}})
    return tracks


class PassDetectionTests(unittest.TestCase):
    def test_stable_same_team_pass_at_actual_fps(self):
        for fps in (10, 25, 29.97, 60):
            with self.subTest(fps=fps):
                needed = PassDetectionConfig().frame_thresholds(fps)["stable_observations"]
                gap = math.ceil(0.12 * fps)
                tracks = history([7] * needed + [None] * gap + [10] * needed)
                result = detect_passes(tracks, fps)
                self.assertEqual(len(result["events"]), 1)
                event = result["events"][0]
                self.assertEqual(event["type"], "pass")
                self.assertEqual((event["player_from"], event["player_to"], event["team"]), (7, 10, 1))
                self.assertEqual(event["frame"], needed + gap)
                self.assertAlmostEqual(event["timestamp"], (needed + gap) / fps)
                self.assertEqual(event["release_frame"], needed - 1)
                self.assertEqual(event["confirmation_frame"], 2 * needed + gap - 1)
                self.assertEqual(event["from_position"], [0, 0])
                self.assertEqual(event["to_position"], [3, 4])
                self.assertAlmostEqual(event["distance"], 5)
                self.assertGreater(event["confidence"], 0)
                self.assertLessEqual(event["confidence"], 1)
                json.dumps(result, allow_nan=False)

    def test_brief_wrong_owner_and_flicker_do_not_make_passes(self):
        needed = PassDetectionConfig().frame_thresholds(25)["stable_observations"]
        for sequence in ([7] * needed + [10] * (needed - 1) + [7] * needed,
                         [7] * needed + [10, 7] * needed,
                         [7] * needed + [None] * 2 + [7] * needed):
            self.assertEqual(detect_passes(history(sequence), 25)["events"], [])

    def test_opponent_possession_breaks_same_team_chain(self):
        needed = PassDetectionConfig().frame_thresholds(25)["stable_observations"]
        result = detect_passes(history([7] * needed + [20] * needed + [10] * needed), 25)
        self.assertEqual(result["events"], [])

    def test_long_unobserved_gap_and_long_flight_are_rejected(self):
        fps = 25
        limits = PassDetectionConfig().frame_thresholds(fps)
        needed = limits["stable_observations"]
        for gap in (["missing"] * (limits["max_unobserved_frames"] + 1),
                    [None] * (limits["max_transition_frames"] + 1)):
            self.assertEqual(detect_passes(history([7] * needed + gap + [10] * needed), fps)["events"], [])

    def test_receiver_must_confirm_before_window_expires(self):
        config = PassDetectionConfig(max_transition_seconds=0.40)
        # At 25 FPS the receiver begins inside the ten-frame window but confirms outside it.
        sequence = [7] * 6 + [None] * 7 + [10] * 6
        self.assertEqual(detect_passes(history(sequence), 25, config)["events"], [])

    def test_short_missing_gaps_can_be_debounced_but_not_counted_as_support(self):
        sequence = [7] * 6 + [None] + [10, "missing", 10, 10, 10, 10, 10]
        result = detect_passes(history(sequence), 25)
        self.assertEqual(len(result["events"]), 1)
        self.assertEqual(result["events"][0]["frame"], 7)
        self.assertEqual(result["events"][0]["confirmation_frame"], 13)
        self.assertEqual(result["event_detection"]["frame_coverage"]["unobserved"], 1)

    def test_no_interpolated_or_ambiguous_or_unknown_team_evidence(self):
        sequence = [7] * 6 + [10] * 6
        tracks = history(sequence)
        for ball in tracks["ball"]:
            ball[1]["is_observed"] = False
        self.assertEqual(detect_passes(tracks, 25)["events"], [])
        self.assertEqual(detect_passes(history([7] * 6 + ["ambiguous"] + [10] * 6), 25)["events"], [])
        tracks = history(sequence)
        for frame in tracks["players"]:
            frame[10].pop("team")
        self.assertEqual(detect_passes(tracks, 25)["events"], [])

    def test_track_replacement_without_covisibility_is_not_a_pass(self):
        tracks = history([7] * 6 + [10] * 6)
        for frame in tracks["players"][6:]:
            del frame[7]
        result = detect_passes(tracks, 25)
        self.assertEqual(result["events"], [])
        self.assertEqual(result["event_detection"]["rejected_identity_transitions"], 1)

    def test_missing_coordinates_keep_event_distance_unknown(self):
        result = detect_passes(history([7] * 6 + [10] * 6, positions=False), 25)
        self.assertEqual(len(result["events"]), 1)
        event = result["events"][0]
        self.assertIsNone(event["from_position"])
        self.assertIsNone(event["to_position"])
        self.assertIsNone(event["distance"])

    def test_receiver_needs_stability_and_events_are_not_repeated(self):
        self.assertEqual(detect_passes(history([7] * 6 + [10] * 5), 25)["events"], [])
        result = detect_passes(history([7] * 6 + [10] * 20 + [7] * 6), 25)
        self.assertEqual([(e["player_from"], e["player_to"]) for e in result["events"]], [(7, 10), (10, 7)])

    def test_json_string_ids_work_and_inputs_are_not_mutated(self):
        tracks = history([7] * 6 + [10] * 6)
        tracks = json.loads(json.dumps(tracks))
        before = deepcopy(tracks)
        self.assertEqual(len(detect_passes(tracks, 25)["events"]), 1)
        self.assertEqual(tracks, before)

    def test_team_conflicting_track_ids_are_excluded(self):
        tracks = history([7] * 6 + [10] * 6)
        tracks["players"][0][10]["team"] = 2
        result = detect_passes(tracks, 25)
        self.assertEqual(result["events"], [])
        self.assertEqual(result["event_detection"]["conflicting_team_track_ids"], [10])

    def test_summary_counts_match_events_and_unknowns_remain_null(self):
        tracks = history([7] * 6 + [10] * 6)
        result = build_analytics(tracks, 25, [1] * 12, {}, PITCH)
        players = {p["player_id"]: p for p in result["players"]}
        self.assertEqual(players[7]["successful_passes"], 1)
        self.assertEqual(players[7]["passes_received"], 0)
        self.assertEqual(players[10]["successful_passes"], 0)
        self.assertEqual(players[10]["passes_received"], 1)
        self.assertIsNone(players[20]["successful_passes"])
        self.assertEqual(result["teams"][0]["total_detected_successful_passes"], 1)
        self.assertIsNone(result["teams"][1]["total_detected_successful_passes"])
        self.assertEqual(result["event_detection"]["status"], "completed")
        json.dumps(result, allow_nan=False)

    def test_empty_missing_ball_and_invalid_timing(self):
        result = detect_passes({}, 25)
        self.assertEqual(result["events"], [])
        self.assertEqual(result["event_detection"]["status"], "insufficient_data")
        tracks = history([7] * 6 + [10] * 6)
        del tracks["ball"]
        self.assertEqual(detect_passes(tracks, 25)["events"], [])
        for fps in (0, -1, float("nan"), float("inf"), None, True):
            with self.subTest(fps=fps), self.assertRaises(ValueError):
                detect_passes({}, fps)
        with self.assertRaises(ValueError):
            PassDetectionConfig(minimum_support_ratio=1.5)

    def test_pass_event_extends_common_format_and_validates_endpoints(self):
        event = PassEvent.at_frame("pass", 10, 25, team=1, player_from=7, player_to=10,
                                   from_position=(0, 0), to_position=(3, 4), distance=5,
                                   release_frame=8, confirmation_frame=15)
        self.assertEqual(event.to_dict()["timestamp"], 0.4)
        self.assertEqual(event.to_dict()["distance"], 5)
        with self.assertRaises(ValueError):
            PassEvent.at_frame("pass", 10, 25, team=1, player_from=7, player_to=7)
        with self.assertRaises(ValueError):
            PassEvent.at_frame("pass", 10, 25, team=1, player_from=7, player_to=10, distance=5)


if __name__ == "__main__":
    unittest.main()
