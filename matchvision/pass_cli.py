"""Recompute pass, probable-shot and tactical analytics from an existing analysis.json without video inference."""
import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from uuid import uuid4

from .analytics.pass_detection import PassDetectionConfig, add_pass_statistics, detect_passes
from .analytics.tactics import build_tactics
from .analytics.shot_detection import ShotDetectionConfig, detect_shots
from .analytics.events import merge_event_detections

logger = logging.getLogger(__name__)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis_json", type=Path)
    parser.add_argument("--output-directory", type=Path, help="Parent for a unique pass-analysis directory")
    parser.add_argument("--stable-seconds", type=float, default=0.24)
    parser.add_argument("--max-transition-seconds", type=float, default=2.0)
    parser.add_argument("--evidence-gap-seconds", type=float, default=0.12)
    parser.add_argument("--max-unobserved-seconds", type=float, default=0.40)
    parser.add_argument("--minimum-support-ratio", type=float, default=0.60)
    parser.add_argument("--shot-calibration", type=Path, help="Input-specific validated goal calibration JSON")
    parser.add_argument("--shot-confidence", type=float, default=0.80)
    parser.add_argument("--shot-cooldown-seconds", type=float, default=1.50)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        source = args.analysis_json.expanduser().resolve()
        result = json.loads(source.read_text(encoding="utf-8-sig"))
        frames = result.get("frames")
        if not isinstance(frames, list) or not frames:
            raise ValueError("Input must contain a nonempty per-frame analysis history")
        if any(frame.get("frame_index") != index for index, frame in enumerate(frames)):
            raise ValueError("Frame history must be contiguous and zero-based; missing frames cannot be compressed")
        metadata = result.get("video") or result.get("match", {})
        fps = metadata.get("fps")
        if not isinstance(result.get("players"), list) or not isinstance(result.get("teams"), list):
            raise ValueError("Input must contain the MatchVision player/team summary lists")
        config = PassDetectionConfig(
            stable_possession_seconds=args.stable_seconds,
            max_transition_seconds=args.max_transition_seconds,
            max_evidence_gap_seconds=args.evidence_gap_seconds,
            max_unobserved_seconds=args.max_unobserved_seconds,
            minimum_support_ratio=args.minimum_support_ratio,
        )
        tracks = {kind: [frame.get(kind, {}) for frame in frames] for kind in ("players", "ball")}
        detection = detect_passes(tracks, fps, config)
        add_pass_statistics(result["players"], result["teams"], detection)
        bounds = result.get("heatmaps", {}).get("bounds")
        vertices = None
        if bounds is not None:
            vertices = [[bounds["x_min"], bounds["y_min"]], [bounds["x_max"], bounds["y_min"]],
                        [bounds["x_max"], bounds["y_max"]], [bounds["x_min"], bounds["y_max"]]]
        shot_calibration = result.get("shot_calibration")
        if args.shot_calibration:
            shot_calibration = json.loads(args.shot_calibration.expanduser().read_text(encoding="utf-8-sig"))
        shots = detect_shots(
            tracks, fps, vertices, calibration=shot_calibration,
            config=ShotDetectionConfig(confidence_threshold=args.shot_confidence,
                                       cooldown_seconds=args.shot_cooldown_seconds),
            pass_events=detection["events"],
        )
        result.update(merge_event_detections(detection, shots, result.get("events", [])))
        result["tactics"] = build_tactics(tracks, result["events"], fps, vertices,
                                          event_detection=detection["event_detection"])
        result["schema_version"] = "2.3"
        parent = args.output_directory.expanduser().resolve() if args.output_directory else source.parent / "pass_detection"
        run = parent / uuid4().hex
        run.mkdir(parents=True, exist_ok=False)
        output_path = run / "pass_analysis.json"
        result["pass_analysis"] = {
            "source_analysis_json": str(source), "result_json": str(output_path),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        result.setdefault("artifacts", {})["pass_analysis_json"] = str(output_path)
        temporary_path = run / "pass_analysis.json.tmp"
        temporary_path.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
        temporary_path.rename(output_path)
        print(f"Detected passes: {len(detection['events'])}")
        print(f"Detection status: {detection['event_detection']['status']}")
        print(f"Probable shots: {len(shots['events'])}; status: {shots['event_detection']['status']}")
        print(f"Analysis JSON: {output_path}")
        return 0
    except Exception:
        logger.exception("Pass analysis failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


