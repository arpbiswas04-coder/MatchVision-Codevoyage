"""Conservative offline joining of player tracklets before downstream analytics."""
from dataclasses import asdict, dataclass
import math
import os

import cv2
import numpy as np


@dataclass(frozen=True)
class ContinuityConfig:
    lost_seconds: float = 2.0
    enabled: bool = True
    max_gap_seconds: float = 0.6
    support_seconds: float = 0.12
    motion_error_heights: float = 0.35
    max_speed_heights_per_second: float = 2.0
    max_lab_distance: float = 18.0
    max_height_ratio: float = 1.25
    crowding_heights: float = 0.9
    max_scene_change: float = 28.0

    @classmethod
    def from_environment(cls):
        config = cls(
            lost_seconds=float(os.getenv("MATCHVISION_TRACK_BUFFER_SECONDS", "2.0")),
            enabled=os.getenv("MATCHVISION_PLAYER_RELINK", "1") != "0",
            max_gap_seconds=float(os.getenv("MATCHVISION_RELINK_GAP_SECONDS", "0.6")),
        )
        if not all(math.isfinite(v) and v > 0 for v in (config.lost_seconds, config.max_gap_seconds)):
            raise ValueError("Tracking timing settings must be positive and finite")
        return config


def foot(track):
    x1, y1, x2, y2 = track["bbox"]
    return np.array([(x1 + x2) / 2, y2], dtype=float)


def appearance(frame, track):
    x1, y1, x2, y2 = track["bbox"]
    width, height = x2 - x1, y2 - y1
    # Central torso avoids most grass, arms, head and shorts.
    left, right = max(0, int(x1 + width * .25)), min(frame.shape[1], int(x1 + width * .75))
    top, bottom = max(0, int(y1 + height * .20)), min(frame.shape[0], int(y1 + height * .50))
    crop = frame[top:bottom, left:right]
    if crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    grass = (hsv[:, :, 0] >= 35) & (hsv[:, :, 0] <= 85) & (hsv[:, :, 1] > 40)
    keep = ~grass
    if keep.sum() < 30 or keep.mean() < .6:
        return None
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB)
    return np.median(lab[keep], axis=0)


def endpoint(rows, frames, fps, config, head):
    count = max(3, math.ceil(config.support_seconds * fps))
    samples = rows[:count] if head else rows[-count:]
    if len(samples) < count:
        return None
    if any((b[0] - a[0]) / fps > .08 for a, b in zip(samples, samples[1:])):
        return None
    elapsed = (samples[-1][0] - samples[0][0]) / fps
    if elapsed <= 0 or elapsed > .3:
        return None
    index, track = samples[0] if head else samples[-1]
    height = track["bbox"][3] - track["bbox"][1]
    if height <= 0:
        return None
    velocity = (foot(samples[-1][1]) - foot(samples[0][1])) / elapsed
    if np.linalg.norm(velocity) > config.max_speed_heights_per_second * height:
        return None
    colors = [appearance(frames[i], item) for i, item in samples]
    if any(color is None for color in colors):
        return None
    color = np.median(colors, axis=0)
    if any(np.linalg.norm(item - color) > config.max_lab_distance for item in colors):
        return None
    return dict(index=index, position=foot(track), velocity=velocity, height=height, color=color)


def relink_players(player_frames, frames, fps, config):
    """No synthetic observations; refuse ambiguous links or simultaneous identities.

    Uses both sides of a gap, so runs after ByteTrack finishes but before camera,
    position, team, speed, possession, rendering and analytics calculations.
    """
    records = {}
    for index, players in enumerate(player_frames):
        for raw_id, track in players.items():
            raw_id = int(raw_id)
            track["tracker_id"] = raw_id
            records.setdefault(raw_id, []).append((index, track))
    parents = {raw_id: raw_id for raw_id in records}
    links = []
    if config.enabled:
        heads = {key: endpoint(rows, frames, fps, config, True) for key, rows in records.items()}
        tails = {key: endpoint(rows, frames, fps, config, False) for key, rows in records.items()}

        def isolated(raw_id, end):
            players = player_frames[end["index"]]
            return all(other == raw_id or np.linalg.norm(foot(track) - end["position"])
                       > config.crowding_heights * end["height"] for other, track in players.items())

        thumbnails = {}

        def scene(index):
            if index not in thumbnails:
                thumbnails[index] = cv2.resize(frames[index], (64, 36)).astype(float)
            return thumbnails[index]

        candidates = []
        for source, tail in tails.items():
            if tail is None or not isolated(source, tail):
                continue
            for target, head in heads.items():
                if target == source or head is None:
                    continue
                gap = (head["index"] - tail["index"]) / fps
                if not 0 < gap <= config.max_gap_seconds or not isolated(target, head):
                    continue
                # Large scene changes are unsafe for image-space re-identification.
                if np.abs(scene(tail["index"]) - scene(head["index"])).mean() > config.max_scene_change:
                    continue
                scale = min(tail["height"], head["height"])
                if max(tail["height"], head["height"]) / scale > config.max_height_ratio:
                    continue
                if np.linalg.norm(tail["color"] - head["color"]) > config.max_lab_distance:
                    continue
                # Both forward and reverse motion must explain the reappearance.
                delta = head["position"] - tail["position"]
                error = max(np.linalg.norm(delta - tail["velocity"] * gap),
                            np.linalg.norm(delta - head["velocity"] * gap))
                if error > config.motion_error_heights * scale:
                    continue
                if np.linalg.norm(delta) > (config.motion_error_heights +
                                           config.max_speed_heights_per_second * gap) * scale:
                    continue
                candidates.append((source, target, gap))

        # Mutual uniqueness: never select a 'best' candidate among plausible teammates.
        for source, target, gap in candidates:
            if sum(a == source for a, _, _ in candidates) != 1:
                continue
            if sum(b == target for _, b, _ in candidates) != 1:
                continue
            parents[target] = source
            links.append({"tracker_from": source, "tracker_to": target, "gap_seconds": gap})

    def root(raw_id):
        while parents[raw_id] != raw_id:
            raw_id = parents[raw_id]
        return raw_id

    # Keep the earliest raw ID as logical ID rather than merely renumbering IDs.
    for index, players in enumerate(player_frames):
        logical = {}
        for raw_id, track in players.items():
            logical_id = root(int(raw_id))
            if logical_id in logical:
                raise ValueError("Player continuity produced overlapping identities")
            logical[logical_id] = track
        player_frames[index] = logical
    return {
        "method": "bytetrack_with_conservative_player_tracklet_links",
        "raw_player_track_count": len(records),
        "logical_player_count": len({root(key) for key in records}),
        "accepted_links": len(links), "links": links,
        "configuration": asdict(config),
        "limitations": [
            "Logical IDs remain estimates, not verified real-world player identities.",
            "No ball/referee relinking or invented gap observations.",
            "Crowded scenes, unavailable appearance, camera changes and ambiguous matches remain separate.",
            "Green jerseys may fail the conservative grass exclusion and remain fragmented.",
        ],
    }

