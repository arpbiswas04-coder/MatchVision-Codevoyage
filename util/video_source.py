"""Bounded-memory access to an original video, preserving source pixel coordinates."""
import math
from pathlib import Path

import cv2


class VideoFrames:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        if not self.path.is_file():
            raise FileNotFoundError(f"Video is unavailable: {self.path}")
        self.capture = cv2.VideoCapture(str(self.path))
        self.next_index = 0
        self.cached_index = -1
        self.cached = None
        if not self.capture.isOpened():
            self.close()
            raise ValueError("Cannot open source video")
        fps = float(self.capture.get(cv2.CAP_PROP_FPS))
        count = self.capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if not math.isfinite(fps) or fps <= 0 or not math.isfinite(count) or count < 1:
            self.close()
            raise ValueError("Video needs valid FPS and frame-count metadata")
        self.count = int(count)
        try:
            first = self[0]
        except Exception:
            self.close()
            raise
        self.metadata = {
            "input_path": str(self.path), "fps": fps, "frame_count": self.count,
            "width": int(first.shape[1]), "height": int(first.shape[0]),
            "duration_seconds": self.count / fps,
        }

    def __len__(self):
        return self.count

    def set_decoded_count(self, count):
        if count < 1:
            raise ValueError("Video has no decodable frames")
        self.count = count
        self.metadata.update(frame_count=count, duration_seconds=count / self.metadata["fps"])

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [self[i] for i in range(*index.indices(len(self)))]
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        if index == self.cached_index:
            return self.cached
        if index != self.next_index:
            if not self.capture.set(cv2.CAP_PROP_POS_FRAMES, index):
                raise OSError(f"Could not seek to source frame {index}")
        ok, frame = self.capture.read()
        if not ok:
            raise OSError(f"Could not decode source frame {index}")
        self.next_index = index + 1
        self.cached_index, self.cached = index, frame
        return frame

    def __iter__(self):
        capture = cv2.VideoCapture(str(self.path))
        try:
            if not capture.isOpened():
                raise OSError("Cannot reopen source video")
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                yield frame
        finally:
            capture.release()

    def close(self):
        self.capture.release()
        self.cached = None

