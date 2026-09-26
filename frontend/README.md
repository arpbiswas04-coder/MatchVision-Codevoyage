# MatchVision web application

Implementation only. No npm installation, build, tests, browser launch, API launch,
inference or video processing was performed by the coding agent.

## Architecture

React + Vite + JavaScript + plain CSS; React Router handles:
- / — landing page.
- /upload — user-selected video, preview, validation and upload.
- /processing/:analysisId — real backend status, polled every three seconds.
- /analysis/:analysisId — summary-based dashboard and printable coach report.

The centralized API module handles multipart upload, status/summary/full-results
functions, errors, URL resolution and a small in-memory completed-summary cache.
The dashboard requests status for filename/lifecycle information, then /summary.
It NEVER automatically requests /results. The explicit "Open full analysis JSON
(large file)" link is the only full-data action exposed in this UI.

The current API schema is used directly:
- teams/players arrays, possession.team_percentages, counts.
- tactics.teams keyed by team ID, with geometry and formation objects.
- heatmaps entries with name/url, highlights entries with video_path.
- annotated_video.browser_available/url/download_url/conversion.
- lists.*.omitted, warnings, tracking and event-detection diagnostics.

No backend or CV algorithm changes were needed. No fake sample videos, fabricated
match metrics, invented events, external fonts, image services or LLM calls are used.
The landing-page pitch is explicitly labelled as a concept illustration.

Only the active dashboard tab is mounted. Heatmaps load one selected image, with
lazy image loading. Highlights mount one selected video, with native playback
controls. Summary data is retained across tab changes; completed jobs are not
polled. Requests and timers are cleaned up on navigation, and local preview URLs
are revoked. A failed connection offers explicit retry rather than pretending
the analysis completed.

## Files created

All paths below are relative to frontend/:
- package.json
- vite.config.js
- index.html
- .env.example
- .gitignore
- README.md
- src/main.jsx
- src/App.jsx
- src/api/matchvision.js
- src/lib/format.js
- src/styles/app.css
- src/pages/Landing.jsx
- src/pages/Upload.jsx
- src/pages/Processing.jsx
- src/pages/Analysis.jsx
- src/components/UI.jsx
- src/components/Overview.jsx
- src/components/MediaPlayer.jsx
- src/components/Players.jsx
- src/components/Heatmaps.jsx
- src/components/Events.jsx
- src/components/Tactics.jsx
- src/components/Highlights.jsx
- src/components/CoachReport.jsx

Existing project file modified: ../README.md, to link this guide.
No backend files were changed for this frontend task.
No package-lock.json was generated because dependencies were not installed.
Your npm install will create it; retain it for reproducible subsequent installs.

## Dependencies and configuration

Use Node.js 22.12+ and npm. package.json declares React, React DOM,
React Router, Vite and the React Vite plugin; there is no UI framework.
Python dependencies and your CUDA environment are unchanged.

VITE_API_BASE_URL is the BACKEND ORIGIN, without a trailing /api:
    http://127.0.0.1:8000

Copy .env.example to .env.local, then adjust if needed. Restart Vite after changes.
Vite environment variables are public browser configuration; never put secrets in
them. For deployment, use an HTTPS backend origin and add the frontend origin to
the backend's explicit MATCHVISION_CORS_ORIGINS. Configure the web host to return
index.html for /upload, /processing/* and /analysis/* history routes.

Local Vite uses strict port 5173 (no silent switch to a port the backend CORS
configuration does not allow). The existing backend permits both
http://127.0.0.1:5173 and http://localhost:5173.

## Manual commands — run these yourself

Terminal 1: start the existing backend (one worker, no reload).
```powershell
Set-Location D:\MatchVision\Football_Analysis
.\.venv\Scripts\Activate.ps1
python -m uvicorn matchvision.api.app:app --host 127.0.0.1 --port 8000 --workers 1 --log-level info 2>&1 | Tee-Object web-backend.log
```

If activation is blocked, use this interpreter directly:
```powershell
Set-Location D:\MatchVision\Football_Analysis
.\.venv\Scripts\python.exe -m uvicorn matchvision.api.app:app --host 127.0.0.1 --port 8000 --workers 1 --log-level info 2>&1 | Tee-Object web-backend.log
```

Terminal 2: install frontend dependencies, configure the backend origin, start Vite.
```powershell
Set-Location D:\MatchVision\Football_Analysis\frontend
node --version
npm --version
npm install
Copy-Item .env.example .env.local
npm run dev 2>&1 | Tee-Object frontend-dev.log
```

Copy the environment file once; do not overwrite your custom settings on later runs.
Vite may warn if your Node.js version is too old. Update Node before continuing.
No Python reinstall or PyTorch replacement is needed for this frontend.

Open:
- http://127.0.0.1:5173 — MatchVision web app.
- http://127.0.0.1:8000/api/health — optional backend health check.
- http://127.0.0.1:8000/docs — optional backend diagnostics; not required for users.

Optional production-build verification (only YOU run it):
```powershell
Set-Location D:\MatchVision\Football_Analysis\frontend
npm run build
# Stop the dev server first because preview uses the same port.
npm run preview
```

## Manual product flow

1. Landing: inspect the desktop layout, brand, feature cards and pipeline.
   "See how it works" scrolls to the pipeline. No real-match figures are shown.
2. Upload: click Analyze match. Browse for or drag in YOUR OWN short football
   video. Confirm filename/size/type, removal/replacement and local preview.
   MP4/AVI/MOV/MKV are supported upload extensions; some codecs cannot preview
   locally, which does not prevent backend validation.
3. Leave optional shot calibration blank unless you have validated JSON for this
   exact camera view. Without it, shots/highlights may legitimately be unavailable.
4. Click Analyze match. It uploads multipart field file (and shot_calibration if
   supplied), stores the returned ID automatically and opens the processing route.
   No copying/pasting IDs or Swagger interaction is needed.
5. Processing: confirm percentage and stage match backend status. Progress can
   stay at one value during inference. Wait for the automatic dashboard redirect.
   Refresh the processing URL once to confirm reconnection to the same job.
6. Overview: check possession/cards against your real summary. Zero is displayed
   as zero; missing values are unavailable or omitted. Expand Analysis notes.
7. Match video: play/pause, seek and fullscreen the annotated MP4. Use the download
   when browser conversion is absent or the codec cannot play. The existing
   annotated video can be silent; controls do not create an audio track.
8. Players: sort Distance, Avg. speed and Max. speed; filter by team. Check logical
   IDs, unavailable measurements, possession times and detected pass counts.
9. Heatmaps: switch Teams/Players/Ball and choose a heatmap. Confirm the player
   team indicator when membership is known. Only the selected image should load.
10. Events: review real events, filter by type and click a timestamp to open the
    annotated video at that time. Shots are labelled Probable shot. No-event
    footage should show a deliberate empty state.
11. Tactics: check the backend's formation hypothesis, width, depth, centroid and
    compactness. Insufficient tracking must show Unknown/unavailable, not a shape
    invented by the UI.
12. Highlights: if clips exist, select one and play/download it. If the backend
    reports no_eligible_events, expect "No eligible highlight events were
    detected for this match." This is not an application error.
13. Coach report: open the report and click Print / Save Report. In print preview,
    choose Save as PDF. Confirm white background, readable text, no site navigation
    and only data-supported observations/limitations. Submitted time comes from the
    job's creation timestamp, not a claim about processing completion time.
14. Refresh the analysis URL while the backend remains running. It should restore
    the dashboard using its registered ID. The landing page can also return to the
    last analysis in this browser tab.
15. Narrow the browser to tablet/mobile widths. Check stacked cards, horizontally
    scrollable tabs/tables, keyboard focus and responsive video.

## Network and error checks

Open browser DevTools → Network, filter to Fetch/XHR:
- Landing should not request /results or use a default video.
- Upload makes one POST /api/matches/upload.
- Processing polls /status approximately every three seconds after each response.
- Polling stops on completed/failed.
- Dashboard loads /summary plus a status request for filename/lifecycle.
- Switching tabs does not reload summary or fetch /results.
- /results is requested only if YOU click the explicit full-analysis link.
- Heatmap/video requests use URLs served by the backend; no image/video binaries
  are embedded in summary JSON.
- Server list limits are shown honestly; the frontend does not silently fetch the
  massive full result to fill truncated lists.

Manual empty/error cases:
- Missing/unsupported/empty files should show clear validation.
- A stopped backend should show a connection error and retry where appropriate.
- Backend 413/503 errors explain upload size or queue availability.
- A failed job shows the backend error and a return-to-upload action.
- A nonexistent/forgotten analysis shows a missing-analysis state.
- Missing heatmap/video files show fallbacks rather than broken-page exceptions.
- Missing events, highlights and tactical data are valid empty states.

The backend remains an in-memory MVP: restarting loses registrations. The
frontend cannot recover such jobs just because output files remain on disk.
If an upload connection is lost after the server accepts it but before the ID is
received, the frontend has no server listing endpoint with which to recover it.
Do not assume navigating away cancels a backend job.

## If something fails, send

- frontend-dev.log (or full npm build/install error) and web-backend.log.
- Browser Console error text, including its stack trace.
- The failing Network request URL, HTTP status and response JSON.
- Screenshot of the page, URL and browser/window width.
- The /summary JSON and analysis ID for data-mapping problems.
- The relevant media filename, media response status and a playback screenshot
  for video/heatmap/highlight problems.
- A print-preview screenshot for report layout issues.
- Node/npm versions for install/build issues.

Do not send the video itself unless needed later. No backend algorithms or
confidence thresholds were changed as part of this frontend implementation.

## Prompt 9 improvements

See [ROBUSTNESS.md](../ROBUSTNESS.md) for current backend streaming changes, pitch-region heatmaps, stable possession/pass partners, tactical windows, report redesign and exact short/long-clip manual checks. This update changes backend analytics as well as UI; the original implementation notes above describe the earlier frontend-only task.

