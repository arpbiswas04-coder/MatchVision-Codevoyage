"""Shared command-line options; importing this module does not open videos."""


def add_highlight_arguments(parser):
    parser.add_argument("--no-highlights", action="store_true")
    parser.add_argument("--highlight-before", type=float, default=5.0, help="Seconds before an event")
    parser.add_argument("--highlight-after", type=float, default=6.0, help="Seconds after an event")
    parser.add_argument("--highlight-merge-gap", type=float, default=1.0)
    parser.add_argument("--highlight-confidence", type=float, default=0.85)
    parser.add_argument("--highlight-max-clips", type=int, default=20)
    parser.add_argument("--highlight-backend", choices=("auto", "ffmpeg", "opencv"), default="auto")
    parser.add_argument("--highlight-source", choices=("original", "annotated"), default="original")


def highlight_options(args):
    return dict(enabled=not args.no_highlights, before_seconds=args.highlight_before,
                after_seconds=args.highlight_after, merge_gap_seconds=args.highlight_merge_gap,
                minimum_confidence=args.highlight_confidence, max_clips=args.highlight_max_clips,
                backend=args.highlight_backend, source=args.highlight_source)
