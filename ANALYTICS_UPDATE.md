# Pass, event and spatial presentation update

Code inspection/edits only. No Python, npm, API, inference, video processing,
tests, builds or benchmarks were executed. Runtime verification is yours.
No new dependencies or environment variables; GPU/model/tracker, streaming video,
upload workflow, shot thresholds and highlight selection were not changed.

## Detection and consistency

Pass evidence uses logical/relinked identities. Existing observed-ball controllers
remain primary. If no controller was assigned, analytics can use a uniquely nearest
foot contact within 0.6 player heights, separated from the second candidate by at
least 0.15 normalized height units. This analytics-only fallback adapts to resolution;
it does not rewrite the existing team-possession overlay. Ambiguous candidates reset
handoff evidence. Interpolated ball frames cannot establish control.

Stable evidence remains 0.24 seconds of observed frames and >=60% run support.
PassDetectionConfig defaults now allow 0.24-second within-run evidence gaps,
0.75-second consecutive missing-ball gaps and 3 seconds from last sender control
to receiver confirmation. All frame thresholds derive from actual FPS. Long gaps
reset evidence; missing frames are not credited as possession. Endpoint movement
requires distinct co-visible players at release OR reception (rather than requiring
both at reception). They must be separated by >=0.5 mean bbox heights, with ball
proximity favouring the expected endpoint owner by >=0.35 heights. If both observed
ball endpoints have transformed coordinates, >=1 m displacement is also required.
These are heuristic safeguards, not proof of intent. Short/occluded passes may
still be missed. Opponent control never produces a successful same-team pass.

Player pass availability no longer requires that player to have possessed the
ball. A player with known team/usable bbox and sufficient observed, unambiguous
ball-evaluation frames receives zero when no pass was detected. An accepted event
also establishes availability. Truly unevaluable players remain null.

successful_passes and its alias passes_sent count accepted pass events by
player_from; passes_received counts player_to. passes_sent_to and
passes_received_from contain partner counts. Team totals count the same pass
events. The table shows totals; hover shows partner details. Full events retain
release/confirmation frames and measured endpoints for inspection.

The common timeline now combines:
- pass: supported same-team stable handoff with endpoint movement evidence;
- shot: existing calibrated probable-shot detector, unchanged;
- possession_change: stable opponent control within the same bounded evidence chain;
- recovery: stable control after >=0.3 seconds of observed unassigned-ball evidence,
  when no recent active controller remains. Missing ball alone is not a recovery.

Events are ordered/deduplicated by type, frame and participants. Confidence tiers
are high >=0.8, medium >=0.6, low otherwise; absent scores remain absent. These are
heuristic scores, NOT probabilities of correctness. No goal, boundary or
interception events are fabricated: goal-line/outcome evidence, verified full-field
boundaries and intended-pass interruption evidence are unavailable in this pipeline.
Reasons are returned in event_detection.unsupported_categories. This remains a
partial observable timeline, not a referee-certified event feed.

Overview, Events and Coach Report consume counts from the same backend timeline.
counts.events covers ALL events; the compact summary still displays only the latest
100 event records and reports omissions. Event-type breakdowns include evaluated
zeroes and leave unavailable detectors null. Full results retain every event.

## Team structure and heatmaps

Existing 10-second tactical windows and conservative formation thresholds remain.
Each window now accumulates per-player coordinate sums/counts, without duplicating
per-frame tracks. Identities need >=20% window position coverage and two observations
to appear in the spatial diagram. Longitudinal bands split when adjacent mean x
positions differ by >=6 m (existing formation-config line gap). These are spatial
bands, not named roles or a guessed formation. Window centroids show movement of
the visible team centre as the user changes windows. Supported/total formation
window counts are exposed; longer videos add windows, not guaranteed classifications.

The SVG uses actual coordinate bounds/proportions, horizontal y and upward x, and
shows average observed positions in the selected window. Averages are not a
simultaneous lineup. Low coverage is explicitly labelled. Summary caps positions
at 40 per window and keeps at most 60 representative windows; full results retain
all observations. Existing supported formations retain their names. Unsupported UI
labels now say 'Formation not confidently classified'; backend status remains
unchanged for compatibility.

Homography inspection confirms only a local 23.32 x 68 m region, with no full-pitch
origin. The detailed heatmap keeps metric proportions. The right-hand pitch now
shows the SAME density with each axis normalized independently to the reference
pitch. Labels state 'NORMALIZED CONTEXT', 'Not global pitch coordinates' and 'Same
samples; not a metric map'. It is NOT a registered, zoomed-out global heatmap.
No midfield/goal location may be inferred from this normalized image. Every team,
player and observed-ball image uses the same renderer. Genuine full-pitch placement
still requires validated global calibration; no calibration was invented.

Coach report adds passing totals/involved players and concise temporal-coverage
observations while retaining snapshot, movement, team shape, events, notes and print.

## Exact file manifest

Created:
- matchvision/analytics/handoff.py
- frontend/src/components/TeamPitch.jsx
- ANALYTICS_UPDATE.md

Modified backend:
- matchvision/analytics/pass_detection.py
- matchvision/analytics/events.py
- matchvision/analytics/temporal_tactics.py
- matchvision/analytics/pitch_rendering.py
- matchvision/analytics/heatmaps.py
- matchvision/api/summary.py

Modified frontend:
- frontend/src/components/Players.jsx
- frontend/src/components/Events.jsx
- frontend/src/components/Overview.jsx
- frontend/src/components/Tactics.jsx
- frontend/src/components/Heatmaps.jsx
- frontend/src/components/CoachReport.jsx
- frontend/src/lib/format.js
- frontend/src/styles/app.css

Modified documentation: BACKEND.md, frontend/README.md.

## Manual startup

Backend PowerShell:
```powershell
Set-Location D:\MatchVision\Football_Analysis
.\.venv\Scripts\python.exe -m uvicorn matchvision.api.app:app --host 127.0.0.1 --port 8000 --workers 1 --log-level info 2>&1 | Tee-Object analytics-api.log
```
Frontend PowerShell (existing installed dependencies):
```powershell
Set-Location D:\MatchVision\Football_Analysis\frontend
npm run dev 2>&1 | Tee-Object analytics-frontend.log
```
Open http://127.0.0.1:5173. Use one backend worker, no --reload. Retain existing
CUDA environment and optional FFmpeg. The in-memory registry still requires the
backend to remain running. Existing outputs are not rewritten; upload a fresh run.

## Manual 30-second verification

1. Save your previous result for comparison, then upload the SAME ~30-second video.
2. Wait for completed. Check existing annotations and GPU log still work.
3. Players: verify simple pass totals, hover partner details and evaluated zeroes.
   Inspect null players against event_detection.evaluated_players in full JSON.
4. Events: watch a few timestamps in the original clip. Look for false oscillations,
   duplicate passes, wrong team transitions or identity substitutions. Report exact
   times/IDs; a higher event count alone is not proof of improved detection.
5. Overview: counts must equal all accepted full-result events, not just the latest
   100 shown in summary. Check the type breakdown and report agree.
6. Tactics: change window selector for both teams. Dots/centroids/bands must come
   from window data; low coverage must not masquerade as a full lineup.
7. Heatmaps: check Team/Player/Ball images, populated normalized context, clear
   non-global labels, lazy loading and full-size link.
8. Coach report: verify team pass totals/top involved players against Players and
   JSON. Inspect print preview without requiring every identity in the report.

After completion, use another PowerShell terminal:
```powershell
Set-Location D:\MatchVision\Football_Analysis
$analysisId = Read-Host 'Completed analysis ID'
$api = "http://127.0.0.1:8000/api/matches/$analysisId"
Invoke-RestMethod "$api/status"
Invoke-WebRequest "$api/summary" -OutFile "$analysisId-summary.json"
Invoke-WebRequest "$api/results" -OutFile "$analysisId-full.json"
$s = Get-Content "$analysisId-summary.json" -Raw -Encoding UTF8 | ConvertFrom-Json
$r = Get-Content "$analysisId-full.json" -Raw -Encoding UTF8 | ConvertFrom-Json
$passes = @($r.events | Where-Object type -eq 'pass')
[PSCustomObject]@{
  AllEvents = @($r.events).Count
  OverviewCount = $s.counts.events
  PassEvents = $passes.Count
  SentTotal = ($r.players | Measure-Object successful_passes -Sum).Sum
  ReceivedTotal = ($r.players | Measure-Object passes_received -Sum).Sum
  TeamPassTotal = ($r.teams | Measure-Object total_detected_successful_passes -Sum).Sum
}
$r.events | Group-Object type | Select-Object Name, Count
$r.players | Select-Object player_id, pass_statistics_available, passes_sent, passes_received
$r.event_detection | ConvertTo-Json -Depth 8
$s.tactics.teams.'1'.temporal.windows | Select-Object start_seconds, end_seconds, coverage_percentage, centroid
```
With evaluated passing, PassEvents, SentTotal, ReceivedTotal and TeamPassTotal
should agree. AllEvents equals OverviewCount when event analysis is available;
null means unavailable, not a count mismatch. The full response is explicitly
requested here for verification, never automatically by the dashboard.

## Manual 2+ minute verification

Repeat the same steps with a real >=120-second (preferably 2–5 minute) clip. Keep
both servers running and record the new ID. Confirm full source duration/frame
count, begin/middle/end overlays, meaningful progress, and first/middle/last
windows. A 120-second clip at 10-second windows normally has 12 windows; a partial
last window is retained with its actual coverage. Longer footage adds evidence
only when tracked positions/control are usable. Check no repeated pass event is
created from lingering possession. Browser Network should still load /summary,
not the full frames. No new duration cap or frame buffer was introduced.

If anything fails send analytics-api.log (first complete traceback), last status
JSON, analysis ID, failure.json if present, both summary/full result sections relevant
to the issue, video duration/FPS/resolution and exact problematic timestamps/IDs.
For UI include analytics-frontend.log, Console error, failing Network response and
screenshot. For bad passes, a short timestamped excerpt or screenshots of release
and receipt are more useful than only a total count. Runtime performance and visual
appearance have not been tested by the coding agent.
