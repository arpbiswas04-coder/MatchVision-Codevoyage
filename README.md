# MatchVision

The FastAPI backend accepts your own video uploads, queues the existing analysis
engine, reports real stage progress, and serves sanitized results and confined
media URLs.

See [BACKEND.md](BACKEND.md) for setup commands, Swagger upload steps, configuration,
the complete file list, expected results and troubleshooting. The existing
README_old.md outside this project folder has been preserved.

Implementation is awaiting manual verification. No code, API requests, videos,
tests, servers or installations were executed during this implementation.
Use one Uvicorn worker without reload for the in-memory MVP queue.

## React web application

The MatchVision frontend is in [frontend/](frontend/). See
[frontend/README.md](frontend/README.md) for the complete file list, environment
configuration, PowerShell startup commands and manual end-to-end verification.
It uses the existing status and lightweight summary APIs; backend algorithms are
unchanged. Frontend installation, builds and runtime verification are pending
your manual testing.
