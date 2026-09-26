"""Command-line entry point for MatchVision. Original entry point: legacy_main.py."""
import argparse
import json
import logging
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Analyze a football video with MatchVision")
    parser.add_argument("input_video", help="Path to the uploaded/source video")
    parser.add_argument("--output-directory", default="outputs", help="Parent directory for unique analysis runs")
    parser.add_argument("--shot-calibration", type=Path, help="Input-specific validated goal calibration JSON; absent means skip shots")
    parser.add_argument("--shot-confidence", type=float, default=0.80)
    parser.add_argument("--shot-cooldown-seconds", type=float, default=1.50)
    from matchvision.highlight_options import add_highlight_arguments, highlight_options
    add_highlight_arguments(parser)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from matchvision import AnalysisError, analyze_match
    from matchvision.analytics import ShotDetectionConfig
    try:
        shot_calibration = None
        if args.shot_calibration:
            shot_calibration = json.loads(args.shot_calibration.expanduser().read_text(encoding="utf-8-sig"))
        shot_config = ShotDetectionConfig(confidence_threshold=args.shot_confidence,
                                         cooldown_seconds=args.shot_cooldown_seconds)
        result = analyze_match(args.input_video, args.output_directory,
                               shot_config=shot_config, shot_calibration=shot_calibration,
                               highlight_config=highlight_options(args))
    except AnalysisError:
        return 1
    except (OSError, ValueError):
        logging.getLogger(__name__).exception("Invalid shot configuration or unreadable calibration file")
        return 1
    print(f"Annotated video: {result['artifacts']['annotated_video']}")
    print(f"Analysis JSON: {result['artifacts']['analysis_json']}")
    shots = result["event_detection"]["shots"]
    print(f"Probable shots: {shots['detected_shots']}; status: {shots['status']}")
    print(f"Highlights: {len(result['highlights'])}; status: {result['highlight_generation']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

