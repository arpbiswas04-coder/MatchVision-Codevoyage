# MatchVision FastAPI backend — manual verification guide

Implementation only: no Python, tests, inference, video processing, package installation,
API requests or server launches were performed by the coding agent.

## Architecture and files

The API queues the existing analysis engine with the upload UUID and a generic
progress callback. The engine still runs without FastAPI from main.py or analyze_match.
No sample video or stub is used by the upload workflow. model/best.pt is unchanged.

Created:
- matchvision/api/__init__.py — API package.
- matchvision/api/app.py — app factory, lifespan, CORS and JSON error handlers.
- matchvision/api/config.py — operator-controlled environment settings.
- matchvision/api/routes.py — upload, status, results, health and media endpoints.
- matchvision/api/jobs.py — locked registry and one-worker background executor.
- matchvision/api/schemas.py — public upload/status schemas.
- matchvision/api/storage.py — UUID confinement, filename sanitization, first-frame inspection.
- matchvision/api/middleware.py — body-size bound before multipart parsing.
- matchvision/api/media.py — optional H.264 conversion, media allowlists and public JSON projection.
- matchvision/progress.py — framework-independent, exception-isolated progress notifications.
- requirements.txt — backend and existing engine dependencies.
- BACKEND.md — this guide.
- README.md — backend entry-point guide (the existing README_old.md is untouched).

Modified:
- matchvision/__init__.py — lazy engine imports; health/docs need no model loading.
- matchvision/analysis.py — optional externally supplied UUID, real progress hooks,
  and no failure-file writes into a pre-existing conflicting run directory.
- matchvision/results.py — forwards the optional progress callback.
- matchvision/analytics/__init__.py — reports heatmap, pass, shot and tactics stages.

Backend structure:
```text
Football_Analysis/
  requirements.txt
  BACKEND.md
  main.py                         # Existing CLI
  model/best.pt                   # Existing weights, unchanged
  matchvision/
    __init__.py
    analysis.py                   # Existing engine
    results.py
    progress.py
    analytics/                    # Existing analytics
    highlights/                   # Existing highlights
    api/
      __init__.py
      app.py
      config.py
      routes.py
      jobs.py
      schemas.py
      storage.py
      middleware.py
      media.py
```

## Start manually in PowerShell

Use the existing Python 3.10+ environment (the repository's .venv is suitable).
No --upgrade flag is needed: retain already satisfactory CV/PyTorch installations.

```powershell
Set-Location D:\MatchVision\Football_Analysis
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn matchvision.api.app:app --host 127.0.0.1 --port 8000 --workers 1 --log-level info 2>&1 | Tee-Object -FilePath api-server.log
```

If PowerShell blocks activation, use the environment interpreter directly:
```powershell
Set-Location D:\MatchVision\Football_Analysis
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn matchvision.api.app:app --host 127.0.0.1 --port 8000 --workers 1 --log-level info 2>&1 | Tee-Object -FilePath api-server.log
```

New backend dependencies: FastAPI, Uvicorn, python-multipart and Pydantic.
requirements.txt also includes the existing engine's ultralytics, supervision,
OpenCV, NumPy, pandas, scikit-learn, torch and torchvision dependencies.
FFmpeg is optional, outside pip. When installed on PATH it enables browser-friendly
H.264 MP4. Without it, analysis still completes and the AVI remains downloadable.
FFprobe remains an optional timing aid for the existing highlight exporter.

Do not use --reload or multiple Uvicorn workers for this in-memory MVP. Keep the
terminal open. Startup should show "Application startup complete" and the port.
Health/docs do not read a video, import YOLO or load the model.

## Upload your own football video with Swagger

1. Open http://127.0.0.1:8000/api/health. Expect:
   `{"status":"ok","service":"MatchVision API"}`.
2. Open http://127.0.0.1:8000/docs.
3. Expand **POST /api/matches/upload** and click **Try it out**.
4. Under **file**, click **Choose File** and select your OWN .mp4, .avi, .mov
   or .mkv file. Start with a short clip while verifying the workflow.
5. Leave **shot_calibration** blank (disable "Send empty value" if Swagger shows it)
   unless you have valid input-specific calibration JSON from the existing shot
   workflow. It accepts JSON text, never a server file path. No calibration is
   borrowed from the sample video. Missing/insufficient calibration means shots
   and highlights may correctly be absent.
6. Click **Execute**. Transfer, file storage and a metadata/first-frame check happen
   before the response; the request does not wait for full YOLO analysis.
7. Expect **202 Accepted** and a body similar to:
```json
{
  "analysis_id": "8a9b8d926ad84fc4a093b80d4fd1e291",
  "status": "queued",
  "progress": 0,
  "stage": "Queued for analysis",
  "error": null,
  "filename": "my_match.mp4",
  "created_at": "2026-09-26T12:00:00+00:00",
  "status_url": "/api/matches/8a9b8d926ad84fc4a093b80d4fd1e291/status",
  "results_url": "/api/matches/8a9b8d926ad84fc4a093b80d4fd1e291/results"
}
```
The example ID is illustrative. Copy the actual analysis_id value from the
response body, without quotes. The worker may have started already, so the first
response may say processing. IDs are UUIDs represented as 32 lowercase hex
characters, preserving the engine's existing directory convention.

## Poll status and retrieve results

In Swagger, expand **GET /api/matches/{analysis_id}/status**, click **Try it out**,
paste the ID and click **Execute**. Repeat manually while the job runs.
You can also open its returned status_url after prefixing http://127.0.0.1:8000.

Progress reports actual frame counters within expensive stages and stage transitions: prepare, detection/tracking,
camera/movement estimates, team assignment, possession, annotated video, statistics,
heatmaps, passes, shots, tactics, highlights, browser conversion and finalisation.
The percentages are coarse stage markers, not elapsed-time estimates. Frame counts can advance while an integer percentage stays unchanged. No random progress or timers
simulate analysis completion.

Completion resembles:
```json
{
  "analysis_id": "8a9b8d926ad84fc4a093b80d4fd1e291",
  "status": "completed",
  "progress": 100,
  "stage": "Completed",
  "error": null,
  "filename": "my_match.mp4",
  "created_at": "2026-09-26T12:00:00+00:00"
}
```

Next execute **GET /api/matches/{analysis_id}/results** in Swagger or open its URL.
It returns the existing statistics, events, tactics, frames and heatmaps, plus
highlight metadata and a new media object. No analytics are fabricated. Local
input paths are removed, artifact/image/clip paths become registered API URLs,
and filesystem-bearing diagnostics are redacted. The original local analysis.json
is preserved on disk; the API serves only api_results.json.

Before completion, results/media return **409** with the job status and stage.
For a failed job, status returns status=failed and a safe error describing the stage;
results return 409 with that same failure information. Unknown or malformed IDs
return **404**.

## Open annotated video, heatmaps and highlights

Use the media URLs returned by the results, prefixed with http://127.0.0.1:8000.

- Browser video: **GET /api/matches/{analysis_id}/video**. Opens H.264 MP4 when
  media.video.browser_available is true.
- AVI download: **GET /api/matches/{analysis_id}/video?download=true**.
  The existing AVI remains intact. If only MP4 exists, this downloads the MP4.
- Heatmap: **GET /api/matches/{analysis_id}/heatmaps/{name}**.
  Copy an actual name from media.heatmaps (e.g. team_1.png or player_7.png).
- Highlight: **GET /api/matches/{analysis_id}/highlights/{name}**.
  Copy an actual generated clip name from media.highlights; do not invent IDs.

MP4 is served inline. AVI highlights download because browser codec support is
unreliable. Empty media.heatmaps/highlights lists are valid if detections or
eligible events are unavailable. Highlights still use the original uploaded
video and do not select ordinary passes.

Without FFmpeg, /video returns 409 with an AVI download URL, while status remains
completed. Check media.video.conversion.status/reason and browser_available.
If browser metadata could not be saved (for example disk exhaustion), the earlier
public result remains available with conversion.status=not_generated; consult logs.

The API does not serve arbitrary filenames, manifests, uploads, models, stubs or
the raw local analysis.json. UUIDs and media basenames are allowlisted, and resolved
paths must remain within the corresponding output directory. API URLs use the
registered analysis, not a client-supplied output root.

## Expected storage after an upload

```text
Football_Analysis/
  uploads/
    <analysis_id>/
      original.mp4                # Or original.avi/.mov/.mkv
  outputs/
    <same_analysis_id>/
      analysis.json               # Existing full local engine result
      api_results.json            # Public result with media URLs
      output_video.avi            # Existing annotated video
      output_video.mp4            # Optional H.264 browser conversion
      heatmaps/
        ball.png                  # Only where data is available
        team_1.png
        team_2.png
        player_<id>.png
      highlights/
        highlights.json
        clip_<uuid>.mp4           # Or silent AVI fallback; zero clips is valid
```

Every upload gets a fresh ID even if the client filename is reused. Filenames are
sanitized for metadata only; stored uploads are always named original.<extension>.
Output creation refuses existing run directories. Rejected uploads are cleaned
up where possible. A failure after engine output creation may also leave a local
failure.json. Raw errors and local paths stay in the server log/local artifacts.

## Configuration

Set environment variables in the PowerShell terminal BEFORE starting Uvicorn.
Defaults are rooted at Football_Analysis, independent of a hardcoded sample path.

| Variable | Default | Meaning |
| --- | --- | --- |
| MATCHVISION_MAX_UPLOAD_BYTES | 2147483648 | 2 GiB file limit |
| MATCHVISION_MAX_ACTIVE_JOBS | 8 | Combined uploading, queued and processing jobs |
| MATCHVISION_UPLOAD_ROOT | Football_Analysis/uploads | Operator-controlled upload storage |
| MATCHVISION_OUTPUT_ROOT | Football_Analysis/outputs | Operator-controlled output storage |
| MATCHVISION_CONVERSION_TIMEOUT_SECONDS | 1800 | Optional FFmpeg browser conversion timeout |
| MATCHVISION_CORS_ORIGINS | http://localhost:5173,http://127.0.0.1:5173 | Comma-separated explicit origins |

Example:
```powershell
$env:MATCHVISION_MAX_UPLOAD_BYTES = "268435456"
$env:MATCHVISION_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
```

The HTTP body bound includes 1 MiB of multipart overhead in addition to the file
limit; streamed file bytes are separately checked. The upload is spooled by the
multipart parser, then copied in chunks, rather than read into one giant byte string.
The lightweight first-frame check does not certify that every later frame is valid.

## Manual failure and isolation checks

These are for YOU to perform; none have been executed by the coding agent.

- Upload two different own videos (or upload one twice): expect different IDs,
  distinct original files and matching isolated output folders.
- Upload a text file, empty video or renamed corrupt file: expect 400/422, no queued
  analysis. A missing multipart file gets 422. Oversized requests/files get 413.
- For a quick size-limit check, restart with MATCHVISION_MAX_UPLOAD_BYTES=1024 and
  try a larger video; then restore the default and restart.
- Request results during processing: expect 409, not partial/fabricated analytics.
- Use an unknown ID or media filename: expect 404.
- If the queue is full, expect 503 with Retry-After=30; running work continues.
- Confirm no D:\ paths appear in the public response and image/clip URLs work.
- With FFmpeg absent, verify status still completes and the AVI download works.
- Compare returned existing analytics against the saved local analysis.json;
  only public path projection and media availability should differ.
- If model/best.pt cannot load, expect status=failed with a stage message and the
  detailed traceback in api-server.log. Do not replace or delete your model to
  manufacture this failure.

## MVP limits and troubleshooting

Run one Uvicorn process with one analysis worker. The registry/queue is in memory:
restarting loses registrations and queued work. Files remain on disk, but old IDs
will return 404 after a restart. There is no resume, history/list endpoint or
automatic cleanup. Graceful shutdown waits for running analysis; queued jobs are
cancelled. A production system needs durable job/result registration, a persistent
queue, worker resource limits, retention and authenticated access. This backend
is intended for local development and binds to loopback in the commands above;
CORS is not authentication.

The engine now uses bounded frame batches and incremental annotation writing.
See [ROBUSTNESS.md](ROBUSTNESS.md) for current memory changes and manual long-clip verification.
Single-camera calibration, uncertain shot detection and variable-FPS limitations
remain as documented by the original analytics. Uploading a new camera view does
not automatically calibrate its pitch/goals.

If anything fails, send:
- The exact command and full relevant api-server.log traceback, including the analysis ID.
- HTTP status and JSON response from upload/status/results or the failing media route.
- A Swagger screenshot showing the request fields and response.
- Video extension, approximate size/duration, and whether FFmpeg is on PATH.
- Relevant api_results.json, analysis.json and failure.json when present.
- For media problems, the media object, clip/image filename and a playback screenshot.
- For missing highlights, event_detection.shots and highlight_generation diagnostics.

The React frontend is documented in frontend/README.md. Manual verification remains required.


## Player continuity and dashboard summary (manual verification pending)

New files: trackers/player_continuity.py and matchvision/api/summary.py.
Modified: trackers/tracker.py, matchvision/analysis.py, matchvision/api/jobs.py,
matchvision/api/routes.py and BACKEND.md.

No tests, API launches, inference or videos were executed by the coding agent.

### Continuity

ByteTrack remains primary, with its activation/matching thresholds unchanged.
The lost-track buffer now represents two seconds at the actual uploaded FPS.
Supervision's installed implementation scales lost_track_buffer from a 30-FPS
reference, so the constructor receives round(30 * configured_seconds). That is
the library's parameter convention, not an assumed video FPS. Each analysis
already constructs a fresh Tracker/ByteTrack instance.

A separate player-only offline pass links nonoverlapping raw tracklets before
any downstream position/identity-dependent calculations. It requires support on
both sides, a short gap, agreeing torso appearance, similar bbox height, compatible
forward AND reverse motion, and an isolated player at each endpoint. Only mutually
unique candidate links are accepted. A large scene-image change rejects a link.
Same-colour teammates are not sufficient evidence. No observations are filled
into gaps, and ball/referee identities are not relinked.

The earliest raw ID is retained as the logical identity (IDs are not just renumbered
to look smaller). Each observed player keeps tracker_id in the full frame records.
All later heatmaps, statistics, team assignments, speeds, distances, possession,
passes, shots and tactics receive the updated player dictionaries.

Configuration:
- MATCHVISION_TRACK_BUFFER_SECONDS: default 2.0, positive seconds.
- MATCHVISION_PLAYER_RELINK: default 1; set 0 to disable additional tracklet linking.
- MATCHVISION_RELINK_GAP_SECONDS: default 0.6, positive maximum endpoint gap.
Set these BEFORE starting the API; they are read when each Tracker is created.
The full result's tracking.configuration records effective settings.

Other conservative ContinuityConfig defaults (code-level):
- support_seconds=0.12, at least three observed frames at each endpoint;
  samples must be within 0.3 seconds and adjacent sample gaps <=0.08 seconds.
- motion_error_heights=0.35, for BOTH forward/reverse prediction errors.
- max_speed_heights_per_second=2.0, bounding image-space speed and displacement.
- max_lab_distance=18.0, Euclidean distance in OpenCV's 8-bit Lab space.
- max_height_ratio=1.25, rejecting strongly different apparent sizes.
- crowding_heights=0.9, rejecting nearby alternative players at either endpoint.
- max_scene_change=28.0, mean absolute 8-bit colour difference of 64x36 thumbnails.

Torso colours need at least 30 non-grass pixels and 60% non-grass coverage.
Green jerseys or small/occluded crops may therefore remain fragmented. These are
heuristics, not verified identities. Camera pans/cuts, crowded play and long gaps
may leave separate IDs. ByteTrack itself can still switch IDs. Reduction is not
guaranteed; avoiding wrong merges is more important than reaching a target count.

### Lightweight endpoint

GET /api/matches/{analysis_id}/summary serves outputs/<id>/api_summary.json.
It uses the same completed-job/404/409 handling as /results. The unchanged full
/results endpoint still serves api_results.json. The worker writes the summary
from the sanitized public projection, so it has no raw local media paths.
A completed job without a cached summary can derive one from its public results.

The summary contains scalar video metadata and duration, player/team statistics,
possession, event counts and compact events, team geometry/formation summaries,
media references, tracking counts and relevant warnings. It excludes frames,
occupancy grids/samples, tactical timelines, formation windows, detailed shot
evidence, and passing-network nodes/edges. Network pass/connection totals remain.
Full details are referenced by full_results_url.

Lists are bounded at 500 players, the latest 100 events, 500 heatmap references
and 500 highlights. lists contains the limits and omitted counts; counts describes
ALL records, not just the displayed subset. Warnings are limited to 30 entries.
A 20-second clip should be far smaller than its full result, but no byte-size or
performance claim has been measured. This endpoint does not invent absent shots.

### Manual comparison

Before uploading again, retain the previous result/analysis JSON locally. IDs
from previous server sessions are not recovered by the in-memory registry.

Start manually:
```powershell
Set-Location D:\MatchVision\Football_Analysis
.\.venv\Scripts\Activate.ps1
python -m uvicorn matchvision.api.app:app --host 127.0.0.1 --port 8000 --workers 1 --log-level info 2>&1 | Tee-Object continuity-api.log
```

Open http://127.0.0.1:8000/docs. In POST /api/matches/upload choose Try it out,
select the SAME original test video, retain the same calibration choice, and
Execute. Copy the new analysis_id. Use GET /api/matches/{analysis_id}/status
until completed, then GET /api/matches/{analysis_id}/summary.

In a second PowerShell terminal:
```powershell
Set-Location D:\MatchVision\Football_Analysis
$analysisId = Read-Host "New completed analysis ID"
$api = "http://127.0.0.1:8000/api/matches/$analysisId"
Invoke-RestMethod "$api/status"
Invoke-WebRequest "$api/summary" -OutFile dashboard-summary.json
Invoke-WebRequest "$api/results" -OutFile full-results.json
$summary = Get-Content dashboard-summary.json -Raw | ConvertFrom-Json
$summary.tracking
$summary.counts
$summary.lists
Get-Item dashboard-summary.json, full-results.json | Select-Object Name, Length

$previousPath = Read-Host "Path to the previous full results or local analysis JSON"
$before = Get-Content -LiteralPath $previousPath -Raw | ConvertFrom-Json
$after = Get-Content full-results.json -Raw | ConvertFrom-Json
[PSCustomObject]@{
    BeforePlayers = @($before.players).Count
    AfterPlayers = @($after.players).Count
    BeforePlayerHeatmaps = @($before.heatmaps.players.PSObject.Properties | Where-Object { $_.Value.image_path }).Count
    AfterPlayerHeatmaps = @($after.heatmaps.players.PSObject.Properties | Where-Object { $_.Value.image_path }).Count
}
```

Expected log: Player continuity: N raw tracks -> M logical players (K accepted links).
Expect M <= N and N-M=K for accepted nonoverlapping chains. The increased ByteTrack
buffer can reduce fragmentation even with K=0. Compare UNIQUE player entries and
player heatmaps, not the maximum numeric ID (ByteTrack also assigns other objects).

Most importantly, open the annotated video via /video (or its AVI download) and
inspect occlusions, crossings and reappearances: the same player should retain
their ID, while two simultaneously visible players must not share one logical ID.
Check tracking.links and frame tracker_id values in full-results.json for specific
joins. Check for implausible speed spikes and wrong team/possession associations.
Fewer heatmaps alone is not proof of correct identities.

For a controlled comparison, restart with these settings, upload the same video,
save the result, then restore defaults and repeat:
```powershell
$env:MATCHVISION_TRACK_BUFFER_SECONDS = "1.0"
$env:MATCHVISION_PLAYER_RELINK = "0"
# Start the API using the command above; upload and save the baseline.
# Stop the server before restoring:
Remove-Item Env:MATCHVISION_TRACK_BUFFER_SECONDS
Remove-Item Env:MATCHVISION_PLAYER_RELINK
```

Send continuity-api.log, the before/after counts, dashboard-summary.json, and a
timestamped screenshot/clip showing any incorrect identity change if something
fails. Full results retain the raw IDs needed to inspect associations.

