# Session Handoff
**Date:** 2026-04-24
**Branch:** main

## Accomplished
- Fixed StatusBar hardcoded mock cluster count — CLUSTERS/ANIMALS stats now driven from live API data
- Fixed LIVE badge — now shows property name from `bounds.name` instead of raw mission_id
- Built M4E Scout Pass architecture: standalone obstacle mapping mode decoupled from thermal census
- New data model: `data/properties/{property_id}/` layer (bounds, obstacles, resolutions) persists across missions
- Updated `core/mock_data.py` — `--mode scout` and `--mode census` CLI args; census writes property layer + mission layer
- Updated `api/server.py` — `/api/scout/{property_id}` endpoint; `build_mission_response()` loads obstacles from property layer first; resolutions write to property level (persistent)
- Updated `companion_app/src/App.jsx` — detects `mission_type: 'scout'` and branches UI accordingly
- Updated `companion_app/src/components/StatusBar.jsx` — scout mode labels, obstacle count stat
- Created `companion_app/src/components/ScoutSummary.jsx` — obstacle type breakdown, AGL range panel, profile save confirmation

## Next Steps
- Build `core/pipeline_runner.py` — watch-folder mode, processes images as they arrive during Pass 1, writes incremental JSON
- Add polling to App.jsx — poll `/api/mission` every 5s while `status == 'processing'`, stop at `pass1_complete`
- Add `last_updated` timestamp to `/api/mission` response for polling
- Status progression: `waiting_for_images → processing (X/N) → pass1_complete`
- Clear zombie uvicorn processes (restart terminal) before next dev session

## Known Issues
- Multiple stale uvicorn processes are bound to port 8000 from this session — won't die from bash; restart terminal to clear
- Vite proxy restored to port 8000 (was temporarily 8002 for testing) — will fall back to mock until clean API is running
- `data/` directory is untracked (gitignore?) — mock data not in repo

## Key Decisions
- **Property-scoped obstacle profiles**: Obstacles keyed by `property_id`, not `mission_id` — persistent across multiple visits to same site. Resolutions also property-scoped.
- **`mission_type` field drives UI mode**: API response includes `mission_type: 'scout' | 'census'` — app branches entirely on this, no URL params or separate routes needed
- **M4E scout pass = obstacle-only**: Scout mode has no clusters, no waypoints on map, no TargetQueue. ScoutSummary replaces it with obstacle breakdown + AGL range.
- **Backwards compatibility preserved**: Legacy `data/detections/` and `data/obstacles/` paths still work as fallback in server

## Uncommitted Changes
⚠️ ALL CHANGES UNCOMMITTED — working on main branch

- `api/server.py` — scout endpoint, property-layer loading, persistent resolutions
- `companion_app/src/App.jsx` — scout/census branch, ScoutSummary integration
- `companion_app/src/components/StatusBar.jsx` — scout mode labels
- `core/mock_data.py` — --mode scout/census args
- `core/waypoint_generator.py` — (minor, verify before commit)
- `companion_app/src/components/ScoutSummary.jsx` — NEW FILE (untracked)
- `data/` — generated mock data (untracked, likely gitignored)
