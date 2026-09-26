# Prompt 9: robustness and analytics/UI changes

Implementation only. No Python, npm, tests, servers, inference, video processing,
API requests or benchmarks were run. Runtime and visual verification are pending.

## Scalability findings and changes

Source inspection found whole-video decoded-frame storage, retained YOLO Results,
and multiple whole-video annotated-frame lists. These scale with decoded pixels,
not compressed upload size. At 1920x1080, 30 FPS and 120 seconds, one uncompressed
BGR frame list alone contains about 22.4 GB of pixel data, before object overhead
or annotation copies. This is an arithmetic estimate, not a measured benchmark.
Large json.dumps strings added another temporary full-result allocation.
Without the failed run's traceback, its specific failure cause is unconfirmed.

The engine now reopens/streams the original video for sequential stages and keeps
one cached frame for random-access continuity checks. It does not resize footage,
cut duration, skip frames, replace ByteTrack or alter YOLO confidence. YOLO defaults
to four frames per batch, transfers results to CPU, and consumes them incrementally.
CUDA OOM splits/retries the current batch, preserving order; a one-frame OOM still
raises a detailed failure. CUDA device 0 / CPU selection is unchanged. The model
is released after tracking. Annotation overlays are written one frame at a time.
Full tracking/analytics dictionaries still grow with duration; memory is reduced,
not constant for all data. Repeated decoding trades disk/CPU work for lower RAM.

JSON is streamed to temporary files and atomically replaced. Full results remain
available; the dashboard still requests only /summary. Frame counters report real
inference, camera, assignment and annotation progress; statistics use stage labels.
No duration limit or analysis-worker timeout was added. Default upload limit is
now 2 GiB; browser conversion timeout is 1800 seconds, optional highlight export
is 600 seconds per export. Optional conversion/export failures preserve analysis.
The server must stay running: the existing single-worker in-memory queue does not
resume after a server restart or operating-system termination.

## Analytics and presentation

Heatmaps use a dark green striped surface, visible region boundary, density colour
and a separate full-pitch reference with halfway/centre/penalty/goal markings.
Actual transformed x is longitudinal, y is lateral; screen horizontal is y and
vertical is x increasing upward. Region proportions are preserved. The current
23.32 m x 68 m calibration has no full-pitch origin: density is NOT stretched onto
an invented whole pitch. A clearly labelled reference pitch carries no data.
Smoothing affects the rendered image only; numeric samples/counts stay unchanged.
The camera-specific calibration remains a limitation for new views.

Player possession counts only observed owner frames in runs accepted by existing
pass-detector stability/support rules. Interpolated, unknown and bridged gap frames
receive no possession credit. Time is possession_frames / actual FPS; percentage
uses all known stable owner frames. Visible players with evaluated stable evidence
can have a real zero; insufficient evidence is null. Team carry-forward possession
remains the existing, separately explained metric. Possession below a minute shows
seconds with fractional precision instead of rounding everything to 0:00.

successful_passes, passes_received, passes_sent_to and passes_received_from derive
from the common pass event timeline. Partner entries are {player_id, count}; team
totals use those same events. Null means no sufficient stable evidence for that
player/team; zero means evaluated with no accepted event. No confidence thresholds
were lowered and no passes/shots were invented.

Team temporal windows default to 10 seconds. Geometry requires at least six usable
players on at least half the window's frames and at least min(5, window_seconds)
seconds of footage. Only qualifying frames contribute to geometry; missing data
is not zero. Windows contain width, depth, mean distance to centroid, centroid,
visible-player count, coverage and conservative formation hypotheses. Summaries
include averages/ranges and widest/narrowest/most compact periods. Dominant formation
needs at least two supported windows and 60% match-time support by default; this
support is not a calibrated probability. Existing eleven-player, stable identity,
goalkeeper separation and calibration requirements remain. Current partial-pitch
calibration correctly keeps full-team formation unknown, even on a longer clip.
Summary includes at most 60 representative windows per team; full results keep all.

The coach report now has snapshot cards, short factual observations, top-five
players by measured distance, team-shape cards, event cards/recent timeline and
separate notes. Print CSS uses readable white cards and keeps rows/cards together.
Missing event/highlight assessment is distinguished from a genuine evaluated zero.

## Files changed

New backend modules:
- util/video_source.py: bounded decoded-frame access.
- matchvision/json_io.py: incremental atomic JSON writes.
- matchvision/analytics/pitch_rendering.py: calibrated-region heatmap renderer.
- matchvision/analytics/temporal_tactics.py: coverage-qualified tactical windows.

Modified backend modules:
- util/video_utils.py
- trackers/tracker.py
- camera_movement_estimator/camera_movement_estimator.py
- matchvision/analysis.py
- matchvision/api/jobs.py
- matchvision/api/config.py
- matchvision/api/summary.py
- matchvision/highlights/planning.py
- matchvision/analytics/pass_detection.py
- matchvision/analytics/__init__.py
- matchvision/analytics/heatmaps.py
- matchvision/analytics/tactics.py

Modified frontend files:
- frontend/src/lib/format.js
- frontend/src/components/Players.jsx
- frontend/src/components/Heatmaps.jsx
- frontend/src/components/Events.jsx
- frontend/src/components/Highlights.jsx
- frontend/src/components/Tactics.jsx
- frontend/src/components/CoachReport.jsx
- frontend/src/styles/app.css

Documentation: ROBUSTNESS.md (new), BACKEND.md and frontend/README.md (updated).
No new dependencies. Keep the working Python/CUDA and Node installations.
FFmpeg remains optional for browser MP4; AVI download survives its absence/failure.

## Configuration

Set before starting the backend; existing environment overrides still apply.

| Setting | Default | Purpose |
| --- | --- | --- |
| MATCHVISION_YOLO_BATCH_SIZE | 4 | Positive inference batch size; adaptive CUDA OOM splitting |
| MATCHVISION_MAX_UPLOAD_BYTES | 2147483648 | Existing setting, raised to 2 GiB |
| MATCHVISION_CONVERSION_TIMEOUT_SECONDS | 1800 | Existing optional browser conversion timeout |
| MATCHVISION_TACTICAL_WINDOW_SECONDS | 10 | Window duration, at least 2 seconds |
| MATCHVISION_TACTICAL_MIN_PLAYERS | 6 | Minimum usable team players per measured frame, at least 2 |
| MATCHVISION_TACTICAL_MIN_COVERAGE | 0.5 | Required fraction of qualifying frames per window, (0,1] |

HighlightConfig.export_timeout_seconds now defaults to 600 (code/config object,
not an environment variable). Existing pass/shot and continuity thresholds remain.
Do not relax tactical quality thresholds merely to force a formation.

## Exact manual startup commands

Backend terminal:
```powershell
Set-Location D:\MatchVision\Football_Analysis
.\.venv\Scripts\python.exe -m uvicorn matchvision.api.app:app --host 127.0.0.1 --port 8000 --workers 1 --log-level info 2>&1 | Tee-Object -FilePath robustness-api.log
```

Frontend terminal (use the already installed dependencies/configuration):
```powershell
Set-Location D:\MatchVision\Football_Analysis\frontend
npm run dev 2>&1 | Tee-Object -FilePath robustness-frontend.log
```

Open http://127.0.0.1:5173. Do not use Uvicorn --reload or multiple workers.
If dependencies were never installed, follow frontend/README.md once first;
this change itself requires no package installation.

## Manual sequence: short clip, then 2–5 minutes

1. Start both terminals. Upload your own 20–30 second clip in the web app. Leave
   shot calibration blank unless you have validated calibration for this view.
2. Confirm upload returns an ID and processing reports actual frame counters.
   The inference log should show your GPU name (CUDA), or CPU when unavailable.
3. Wait for completed, 100%. Inspect annotated video at beginning/middle/end for
   IDs, team colours, ball/possession, camera and speed/distance overlays.
4. Check Team/Player/Ball heatmap selectors, full-size link, dark styling, axes,
   partial-region disclaimer and reference pitch. Only selected images should load.
5. Check player possession seconds/percentages and pass partner lists. Confirm
   partner counts sum to totals; all team/player pass totals agree with events.
   Missing evidence must remain Unavailable; do not expect forced passes/shots.
6. Check tactical window selector, coverage, ranges and plain-language labels.
   Low-coverage geometry is unavailable and unsupported formations remain Unknown.
7. Open coach report and Print / Save Report; inspect A4/Letter print preview for
   readable tables/cards, no navigation and separated notes.
8. Repeat using a REAL >=120-second clip, preferably 2–5 minutes. Keep both servers
   running. Do not shorten the clip to pass verification. Record the new ID.
9. Confirm the output frame count/duration covers the entire source. Observe RAM
   and GPU memory in Task Manager if useful. No specific speed/memory result has
   been measured by the coding agent. Optional MP4 conversion may take additional
   time; a failed conversion must still leave completed analysis and downloadable AVI.
10. Browser DevTools Network should show /summary, not automatic /results. Inspect
    the first, middle and last tactical windows and the full-length output video.

Use a third PowerShell terminal after each completed run:
```powershell
Set-Location D:\MatchVision\Football_Analysis
$analysisId = Read-Host 'Analysis ID from the dashboard URL'
$api = "http://127.0.0.1:8000/api/matches/$analysisId"
Invoke-RestMethod "$api/status" | ConvertTo-Json -Depth 8
Invoke-WebRequest "$api/summary" -OutFile "$analysisId-summary.json"
$summary = Get-Content "$analysisId-summary.json" -Raw -Encoding UTF8 | ConvertFrom-Json
$summary.video
$summary.counts | ConvertTo-Json -Depth 5
$summary.players | Select-Object player_id, possession_frames, possession_time_seconds, successful_passes, passes_received
$summary.tactics.teams.'1'.temporal | ConvertTo-Json -Depth 12
$summary.event_detection | ConvertTo-Json -Depth 8
$summary.highlight_generation | ConvertTo-Json -Depth 8
# Full response is deliberately large; request explicitly only when needed.
Invoke-WebRequest "$api/results" -OutFile "$analysisId-results.json"
Get-Item "$analysisId-summary.json", "$analysisId-results.json" | Select-Object Name, Length
```

Expected artifacts under outputs/<analysis_id>/:
analysis.json, api_results.json, api_summary.json, output_video.avi, heatmaps/*.png,
optional output_video.mp4 and highlights/ exports/manifest. Existing output folders
are not rewritten; upload again to obtain the new schema/images.

## If the long clip fails

Send the ID, exact startup command/environment overrides, upload response and last
/status JSON (status, progress, stage, error), plus robustness-api.log including the
complete FIRST traceback and preceding frame counters. Include failure.json from
outputs/<id>/ when present; it records stage, exception type, message and traceback.
A hard process kill/OOM termination may leave no failure.json: report whether the
backend terminal exited, server restarted, laptop slept or disk filled.

Also send video duration, resolution, FPS, codec, file size, free RAM/disk space,
and Task Manager CPU/RAM/GPU screenshots around failure if captured. For API/UI
issues include failing HTTP URL/status/body, browser Console stack, Network entry,
robustness-frontend.log and screenshot. For analytics send summary JSON plus the
relevant analysis.json possession/events/tactics/heatmap sections. For conversion
send annotated_video.conversion diagnostics; for print send preview screenshots.
Review local logs for private paths before sharing. No need to send the video
unless requested later. If CUDA OOM persists, manually retry after setting
$env:MATCHVISION_YOLO_BATCH_SIZE = '1' before restarting the backend; this does not
change resolution, frame count or confidence thresholds.
