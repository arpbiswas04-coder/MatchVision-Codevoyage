from ultralytics import YOLO
import supervision as sv
import pickle
import os
import cv2
import numpy as np
import pandas as pd
import logging
import torch
import gc
from itertools import islice
from .player_continuity import ContinuityConfig, relink_players


def get_center_of_bbox(bbox):
    x1, y1, x2, y2 = bbox
    return int((x1 + x2) / 2), int((y1 + y2) / 2)


def get_bbox_width(bbox):
    return bbox[2] - bbox[0]

def get_foot_position(bbox):
    x1,y1,x2,y2 = bbox
    return int((x1+x2)/2),int(y2)

class Tracker:
    def __init__(self, model_path, frame_rate=30):
        self.device = 0 if torch.cuda.is_available() else "cpu"
        device_name = (
            f"{torch.cuda.get_device_name(0)} (CUDA)"
            if self.device == 0 else "CPU"
        )
        # Use the application's logger so both CLI and API workers show selection.
        logging.getLogger("matchvision.inference").info(
            "MatchVision inference device: %s", device_name
        )
        self.model = YOLO(model_path)
        self.frame_rate = frame_rate
        self.continuity_config = ContinuityConfig.from_environment()
        # Supervision scales this parameter from its 30-FPS reference to actual FPS.
        self.tracker = sv.ByteTrack(
            frame_rate=frame_rate,
            lost_track_buffer=max(1, round(30 * self.continuity_config.lost_seconds)))

    def add_position_to_tracks(sekf, tracks):
        for object, object_tracks in tracks.items():
            for frame_num, track in enumerate(object_tracks):
                for track_id, track_info in track.items():
                    bbox = track_info['bbox']
                    if object == 'ball':
                        position = get_center_of_bbox(bbox)
                    else:
                        position = get_foot_position(bbox)
                    tracks[object][frame_num][track_id]['position'] = position

    def interpolate_ball_positions(self,ball_positions):
        ball_positions = [x.get(1,{}).get('bbox',[np.nan] * 4) for x in ball_positions]
        df_ball_positions = pd.DataFrame(ball_positions,columns=['x1','y1','x2','y2'])

        df_ball_positions = df_ball_positions.interpolate()
        df_ball_positions = df_ball_positions.bfill()

        ball_positions = [{1: {"bbox": x}} if np.isfinite(x).all() else {}
                          for x in df_ball_positions.to_numpy().tolist()]

        return ball_positions

    def detect_frames(self, frames, progress_callback=None):
        """Yield CPU results in small batches; retain no match-long tensor list."""
        batch_size = int(os.getenv("MATCHVISION_YOLO_BATCH_SIZE", "4"))
        if batch_size < 1:
            raise ValueError("MATCHVISION_YOLO_BATCH_SIZE must be positive")
        iterator = iter(frames)
        processed = 0

        def predict(batch):
            try:
                results = self.model.predict(batch, conf=0.1, verbose=False, device=self.device)
                cpu_results = [result.cpu() for result in results]
                del results
                return cpu_results
            except torch.cuda.OutOfMemoryError:
                if self.device == "cpu" or len(batch) <= 1:
                    raise
                gc.collect()
                torch.cuda.empty_cache()
                return None

        try:
            while batch := list(islice(iterator, batch_size)):
                pending = [batch]
                while pending:
                    part = pending.pop(0)
                    results = predict(part)
                    if results is None:
                        gc.collect()
                        torch.cuda.empty_cache()
                        batch_size = max(1, len(part) // 2)
                        logging.getLogger("matchvision.inference").warning(
                            "CUDA memory pressure; retrying with batch size %d", batch_size)
                        pending[0:0] = [part[:batch_size], part[batch_size:]]
                        continue
                    for result in results:
                        yield result
                        processed += 1
                    del results
                if progress_callback:
                    progress_callback(processed, len(frames))
                del batch
        finally:
            if hasattr(iterator, "close"):
                iterator.close()

    def release_model(self):
        self.model = None
        gc.collect()
        if self.device != "cpu":
            torch.cuda.empty_cache()

    def get_object_tracks(self, frames, read_from_stub=False, stub_path=None, progress_callback=None):
        if read_from_stub and stub_path is not None and os.path.exists(stub_path):
            with open(stub_path, 'rb') as f:
                tracks = pickle.load(f)
            return tracks

        detections = self.detect_frames(frames, progress_callback)

        tracks = {
            "players": [],
            "referees": [],
            "ball": []
        }
        for frame_num, detection in enumerate(detections):
            cls_names = detection.names
            cls_names_inv = {v: k for k, v in cls_names.items()}

            detection_supervision = sv.Detections.from_ultralytics(detection)
            for obj_ind, class_id in enumerate(detection_supervision.class_id):
                if cls_names[class_id] == 'goalkeeper':
                    detection_supervision.class_id[obj_ind] = cls_names_inv['player']

            detection_with_tracks = self.tracker.update_with_detections(detection_supervision)
            tracks["players"].append({})
            tracks["referees"].append({})
            tracks["ball"].append({})

            for frame_detection in detection_with_tracks:
                bbox = frame_detection[0].tolist()
                cls_id = frame_detection[3]
                track_id = frame_detection[4]

                if cls_id == cls_names_inv['player']:
                    tracks["players"][frame_num][track_id] = {"bbox": bbox}

                if cls_id == cls_names_inv['referee']:
                    tracks["referees"][frame_num][track_id] = {"bbox": bbox}

            for frame_detection in detection_supervision:
                bbox = frame_detection[0].tolist()
                cls_id = frame_detection[3]

                if cls_id == cls_names_inv['ball']:
                    tracks["ball"][frame_num][1] = {"bbox": bbox}

        if hasattr(frames, "set_decoded_count"):
            frames.set_decoded_count(len(tracks["players"]))
        self.identity_diagnostics = relink_players(
            tracks["players"], frames, self.frame_rate, self.continuity_config)
        logging.getLogger("matchvision.tracking").info(
            "Player continuity: %d raw tracks -> %d logical players (%d accepted links)",
            self.identity_diagnostics["raw_player_track_count"],
            self.identity_diagnostics["logical_player_count"],
            self.identity_diagnostics["accepted_links"])

        if stub_path is not None:
            with open(stub_path, 'wb') as f:
                pickle.dump(tracks, f)

        return tracks

    def draw_ellipse(self, frame, bbox, color, track_id=None):
        y2 = int(bbox[3])

        x_center, _ = get_center_of_bbox(bbox)
        width = get_bbox_width(bbox)

        cv2.ellipse(
            frame,
            center=(x_center, y2),
            axes=(int(width), int(0.35 * width)),
            angle=0.0,
            startAngle=-45,
            endAngle=235,
            color=color,
            thickness=2,
            lineType=cv2.LINE_4
        )

        rect_width=40
        rect_height = 20
        x1_rect= x_center-rect_width//2
        x2_rect = x_center + rect_width // 2
        y1_rect = (y2 - rect_height//2) +15
        y2_rect = (y2 + rect_height // 2) + 15

        if track_id is not None:
            cv2.rectangle(frame,
                          (int(x1_rect),int(y1_rect)),
                          (int(x2_rect), int(y2_rect)),
                          color,
                          cv2.FILLED)

            x1_text = x1_rect+12
            if track_id>99:
                x1_text -=10

            cv2.putText(
                frame,
                f"{track_id}",
                (int(x1_text),int(y1_rect+15)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0,0,0),
                2
            )

        return frame

    def draw_triangle(self,frame,bbox,color):
        y= int(bbox[1])
        x,_ = get_center_of_bbox(bbox)

        triangle_points = np.array([
            [x,y],
            [x-10,y-20],
            [x+10,y-20]
        ])
        cv2.drawContours(frame,[triangle_points],0,color,cv2.FILLED)
        cv2.drawContours(frame, [triangle_points], 0, (0,0,0),2)

        return frame

    def draw_team_ball_control(self, frame, frame_num, team_ball_control):

        overlay = frame.copy()
        cv2.rectangle(overlay, (1350, 850), (1900, 970), (255, 255, 255), -1)
        alpha = 0.3
        cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

        team_ball_control_till_frame = team_ball_control[:frame_num + 1]

        team_1_num_frames = team_ball_control_till_frame[team_ball_control_till_frame == 1].shape[0]
        team_2_num_frames = team_ball_control_till_frame[team_ball_control_till_frame == 2].shape[0]
        known_frames = team_1_num_frames + team_2_num_frames
        team_1 = team_1_num_frames / known_frames if known_frames else 0
        team_2 = team_2_num_frames / known_frames if known_frames else 0

        cv2.putText(frame, f"Team 1 Ball Control: {team_1 * 100:.2f}%", (1400, 900), cv2.FONT_HERSHEY_SIMPLEX, 1,
                    (0, 0, 0), 3)
        cv2.putText(frame, f"Team 2 Ball Control: {team_2 * 100:.2f}%", (1400, 950), cv2.FONT_HERSHEY_SIMPLEX, 1,
                    (0, 0, 0), 3)

        return frame

    def draw_annotations(self, video_frames, tracks, team_ball_control):
        # Legacy list-returning API remains available.
        return list(self.iter_annotations(video_frames, tracks, team_ball_control))

    def iter_annotations(self, video_frames, tracks, team_ball_control):

        for frame_num, frame in enumerate(video_frames):
            frame = frame.copy()

            player_dict = tracks["players"][frame_num]
            ball_dict = tracks["ball"][frame_num]
            referee_dict = tracks["referees"][frame_num]

            for track_id, player in player_dict.items():
                color = player.get("team_color",(0,0,255))
                frame = self.draw_ellipse(frame, player["bbox"], color, track_id)

                if player.get('has_ball',False):
                    frame = self.draw_triangle(frame, player["bbox"], (0,0,255))

            for _, referee in referee_dict.items():
                frame = self.draw_ellipse(frame, referee["bbox"], (0, 255, 255))

            for _, ball in ball_dict.items():
                frame = self.draw_triangle(frame, ball["bbox"], (0, 255, 0))

            frame = self.draw_team_ball_control(frame, frame_num, team_ball_control)

            yield frame






