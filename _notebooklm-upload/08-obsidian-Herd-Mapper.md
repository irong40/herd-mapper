# Herd Mapper — Adaptive Two-Pass Wildlife Census

**Type:** SAI internal tool — adaptive thermal wildlife survey system
**Repo:** `D:\Projects\herd-mapper\`
**Status:** Phase 1 MVP active (as of 2026-04-24)
**Primary target:** Deer census (extensible to other wildlife)

## Why
Existing census tools fly fixed grids and rely on manual review. Herd Mapper does a Pass 1 thermal recon to find animals, then routes autonomously to detected areas for a Pass 2 investigation pass — more efficient and produces a more defensible deliverable (thermal + RGB pair per detection).

## Architecture (current — "no-land" target)
- **Pass 1**: 200 ft AGL thermal grid, M4T rangefinder running. Quick Transfer streams images to RC Pro → laptop mid-flight.
- **Pipeline runs during Pass 1**: watch-folder mode processes images as they arrive; detections ready by end of Pass 1.
- **Pass 1 ends**: drone holds altitude, **does NOT land**.
- **Operator reviews** (30–60 sec window): companion app shows clusters + obstacle alerts.
- **Pass 2**: operator approves → loads KMZ into DJI Pilot 2 → drone executes immediately, no relaunch.
- **Obstacle map**: rangefinder + pattern inference (fence posts, power line poles) + OSM + catenary math.
- **Human-in-the-loop**: HIGH auto-classify · MEDIUM soft alert · LOW hard stop (operator confirms).
- **Guy wires**: tower → 1.5× height exclusion cone.
- **Ground station**: React/Vite companion app in RC Pro browser, wireless HDMI to external monitor.

## Tech Stack
Python 3.12 · FastAPI · React/Vite · Leaflet · Tailwind · Lucide React · sentinel-core (local editable install)

## Built (as of 2026-04-24)

### Python core (`core/`)
- `blob_detector.py` — thermal images → GPS clusters, uses sentinel-core
- `obstacle_mapper.py` — rangefinder + OSM → obstacle profile JSON
- `waypoint_generator.py` — clusters + obstacles → Pass 2 KMZ (DJI WPML format); also `generate_pass1_grid()` for pre-mission planning
- `mock_data.py` — generates demo data; supports `--mode scout` and `--mode census`

### API (`api/server.py`)
- FastAPI: `GET /api/mission`, `GET /api/scout/{property_id}`, `POST /api/resolve`, `GET /api/health`
- Property-scoped resolutions persist to `data/properties/{property_id}/`
- Serves React build as static files for field deployment (one URL, one process)

### Companion app (`companion_app/`)
- Satellite tiles (ESRI World Imagery + CARTO dark labels) — tactical, not a road map
- Reticle cluster markers (crosshair + deer count + glow, pulse on selected)
- Fly-to on cluster/waypoint select; alert resolution unlocks waypoints reactively
- "Initiate Pass 2" launch bar — gated until all LOW alerts resolved
- LIVE badge (server connected) vs DEMO badge (mockData fallback)
- Custom SVG icons: DeerCluster, TowerHazard, PowerLine, Fence, Waypoint, Drone, Lock, CheckReady
- Scout mode: ScoutSummary.jsx (obstacle breakdown, AGL panel, profile save)

### sentinel_core extraction (2026-04-24)
- `sentinel_core/spatial.py` — haversine, parse_kml, kml_center, kml_bbox, METERS_PER_LAT_DEG (consolidated from Sortie + Herd Mapper)
- 13 sentinel-core tests pass · 315 Sortie tests pass after refactor

## Parked — Next Session (priority order)
1. **App.jsx scout routing** — currently always fetches `/api/mission`; scout sessions don't load from `/api/scout/{property_id}`. Add query-param routing or URL-driven mode.
2. **M4E obstacle review** (other terminal work) — when landed, compare obstacle schema to `obstacle_mapper.py`'s `Obstacle` dataclass; unify in `sentinel_core.spatial` if they differ.
3. **Watch-folder pipeline runner** — `core/pipeline_runner.py` watches `data/incoming/{mission_id}/`, runs blob_detector + obstacle_mapper as images arrive; `last_updated` on `/api/mission`; App.jsx polls every 5s while `status == 'processing'`. Status progression: `waiting_for_images → processing (X/N) → pass1_complete`.
4. **server.py haversine cleanup** — inline `haversine_m` should use `sentinel_core.spatial.haversine`.

## Pending (later)
- `species_classifier.py` — Wildlife Insights API wrapper
- `report_generator.py` — SAI Report Builder integration
- **Phase 2**: Manifold 3 onboard via PSDK — eliminates inter-sortie download window. blob_detector plugs in with minimal changes (frame input instead of file path). DJI Developer Program membership confirmed; App Key not yet registered.

## Hardware (verified 2026-04-25)
Drone is **M4E** (corrected from M4T in older notes).

## Run / Develop
- Mock data: `python core/mock_data.py` (run first)
- API: `uvicorn api.server:app --host 0.0.0.0 --port 8000`
- Companion app: `cd companion_app && npm run dev` (port 5173, proxies `/api` to 8000)

## Known Issues
- Stale uvicorn zombie processes on port 8000 — restart terminal before next session

## Key References
- `CLAUDE.md` — full spec
- `docs/ADR-001` — two-sortie MVP rationale (SUPERSEDED by no-land architecture)
- `docs/ADR-002` — companion app as web app
