"""Export existing events without rerunning detection or modifying the input JSON."""
import argparse
import json
import logging
from pathlib import Path
import re
from uuid import uuid4

from .highlight_options import add_highlight_arguments, highlight_options


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis_json", type=Path)
    parser.add_argument("--input-video", required=True, type=Path,
                        help="Explicit original video; never read a source path from event JSON")
    parser.add_argument("--annotated-video", type=Path,
                        help="Required only when explicitly selecting annotated highlights")
    parser.add_argument("--output-directory", type=Path, default=Path("outputs"))
    add_highlight_arguments(parser)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        result = json.loads(args.analysis_json.read_text(encoding="utf-8-sig"))
        analysis_id = result.get("analysis_id")
        if not isinstance(analysis_id, str) or not re.fullmatch(r"[0-9a-f]{32}", analysis_id):
            raise ValueError("Analysis ID must be a generated 32-character hexadecimal identifier")
        root = args.output_directory.expanduser().resolve()
        directory = (root / analysis_id).resolve()
        directory.relative_to(root)
        directory.mkdir(parents=True, exist_ok=True)
        try:
            from .highlights import generate_highlights
            extra = generate_highlights(
                result.get("events", []), args.input_video, directory,
                config=highlight_options(args), annotated_video_path=args.annotated_video,
                video_metadata=result.get("video"))
            json.dumps(extra, allow_nan=False)
            result.update(extra)
        except Exception:
            logging.getLogger(__name__).exception("Optional highlight stage failed")
            result.update(highlights=[], highlight_generation={
                "status": "failed", "warnings": ["Highlight generation unavailable; see the local log."]})
        snapshot = directory / f"highlight_analysis_{uuid4().hex}.json"
        with snapshot.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, indent=2, allow_nan=False)
        print(f"Analysis snapshot: {snapshot}")
        print(f"Highlights: {len(result['highlights'])}; status: {result['highlight_generation']['status']}")
        return 0
    except (OSError, ValueError, TypeError, AttributeError):
        logging.getLogger(__name__).exception("Could not read analysis or save highlight results")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
