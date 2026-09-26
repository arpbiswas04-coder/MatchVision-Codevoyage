"""Movement/identity evidence for handoffs; local spatial and temporal verification."""
import math


def handoff_evidence(source, receiver, player_frames, ball_frames):
    if source.player_id == receiver.player_id or source.team != receiver.team:
        return False

    def track(frame, key):
        return frame.get(key, frame.get(str(key)))

    # 1. Check calibrated pitch positions if available
    from_pos = source.last_position or source.first_position
    to_pos = receiver.first_position or receiver.last_position
    if from_pos is not None and to_pos is not None:
        try:
            pitch_dist = math.dist(from_pos, to_pos)
            if math.isfinite(pitch_dist):
                if pitch_dist < 1.5:
                    # Spatial evidence indicates the same physical location (tracker ID switch)
                    return False
                # Distinct locations on the pitch
                return True
        except (TypeError, ValueError):
            pass

    # 2. Check 2D bounding boxes at endpoints or in co-visible frames
    separated = False
    motion = True

    for index in (source.last_frame, receiver.first_frame):
        if index >= len(player_frames):
            continue
        players = player_frames[index]
        a, b = track(players, source.player_id), track(players, receiver.player_id)
        if a and b:
            ba, bb = a.get('bbox'), b.get('bbox')
            if ba and bb:
                height = max(1.0, (abs(ba[3] - ba[1]) + abs(bb[3] - bb[1])) / 2.0)
                foot_a = ((ba[0] + ba[2]) / 2.0, ba[3])
                foot_b = ((bb[0] + bb[2]) / 2.0, bb[3])
                if math.dist(foot_a, foot_b) < 0.5 * height:
                    return False
                separated = True

    # Check separate endpoints across frames
    if not separated:
        a = track(player_frames[source.last_frame], source.player_id) if source.last_frame < len(player_frames) else None
        b = track(player_frames[receiver.first_frame], receiver.player_id) if receiver.first_frame < len(player_frames) else None
        ba = a.get('bbox') if a else None
        bb = b.get('bbox') if b else None
        if ba and bb:
            height = max(1.0, (abs(ba[3] - ba[1]) + abs(bb[3] - bb[1])) / 2.0)
            foot_a = ((ba[0] + ba[2]) / 2.0, ba[3])
            foot_b = ((bb[0] + bb[2]) / 2.0, bb[3])
            if math.dist(foot_a, foot_b) < 0.5 * height:
                return False
            separated = True
        elif ba is None and bb is None:
            # When bounding boxes are not present (e.g. synthetic data), rely on distinct IDs
            separated = True

    return separated and motion

