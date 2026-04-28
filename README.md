# Herd Mapper
**Sentinel Aerial Inspections — Adaptive Wildlife Census System**

Herd Mapper is a two-pass drone census system for M4T/M4E operations. Pass 1 flies a thermal grid to detect animal clusters. The Outer Guard tiles the airspace for hazards. Pass 2 routes autonomously to flagged clusters for dual thermal+RGB capture.

## Architecture

```
Pass 1 (M4T thermal grid, 200 ft AGL)
    ↓ DJI Quick Transfer → laptop
The Outer Guard  ←  rangefinder telemetry + OSM Overpass API
    ↓ tiled airspace (Cowans map)
Blob Detector  ←  thermal images
    ↓ GPS clusters
Waypoint Generator
    ↓ Pass 2 KMZ (DJI WPML)
Companion App  ←  operator reviews clusters + resolves alerts
    ↓ operator approves
Pass 2 (autonomous, drone already airborne)
```

### The Outer Guard (Terminology)
- **Cowan** — a detected hazard (power line, tower, fence)
- **Tiling** — the process of scanning and securing a mission area for safe flight
- **Duly Tiled** — airspace fully mapped and cleared for autonomous Pass 2

## Project Structure

```
core/
  blob_detector.py       # Thermal images → GPS deer clusters
  outer_guard.py         # The Outer Guard: rangefinder + OSM → Cowan map
  waypoint_generator.py  # Clusters + Cowans → Pass 2 KMZ (DJI WPML)
  mock_data.py           # Demo data generator (scout + census modes)

api/
  server.py              # FastAPI: serves pipeline data + React build

companion_app/           # React/Vite operator interface
  src/
    App.jsx
    components/
      PropertyMap.jsx    # Satellite map, obstacle overlays, cluster markers
      AlertPanel.jsx     # Confidence-tiered hazard alerts + resolve flow
      TargetQueue.jsx    # Pass 2 waypoints, locked/ready state, launch gate
      StatusBar.jsx      # Mission HUD (drone, status, cluster/animal counts)
      ScoutSummary.jsx   # Scout mode: obstacle profile, AGL range

data/
  properties/{id}/       # Persistent property layer (bounds, obstacles, lake)
  missions/{id}/         # Per-mission data (detections, config, flight log)

tests/
  test_outer_guard.py
```

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
cd companion_app && npm install
```

### 2. Generate demo data

```bash
# Full census demo (detections + obstacle profile)
python core/mock_data.py --mode census

# Scout pass only (obstacle mapping, no detections)
python core/mock_data.py --mode scout
```

### 3. Start the API server

```bash
uvicorn api.server:app --reload --port 8000
```

### 4. Start the companion app

```bash
cd companion_app && npm run dev
# Opens at http://localhost:5173
```

**URL params:**
- `http://localhost:5173` — census mode (default, mission `demo`)
- `http://localhost:5173?mission=<id>` — specific census mission
- `http://localhost:5173?scout=<property_id>` — scout mode

## Pipeline (real mission)

```bash
# After Pass 1 images downloaded from drone:

# 1. Tile the airspace (identify Cowans)
python core/outer_guard.py \
    --log data/missions/MISSION_ID/flight_log.csv \
    --output data/obstacles/ \
    --bounds '{"north":36.79,"south":36.77,"east":-76.44,"west":-76.46}'

# 2. Detect animal clusters
python core/blob_detector.py \
    --mission data/missions/MISSION_ID \
    --output data/detections/

# 3. Generate Pass 2 waypoints
python core/waypoint_generator.py \
    --detections data/detections/MISSION_ID_detections.json \
    --obstacles data/obstacles/MISSION_ID_tiled_airspace.json \
    --output data/missions/MISSION_ID/pass2.kmz

# 4. Open companion app, review alerts, initiate Pass 2
```

## Companion App — Operator Flow

1. **LIVE badge** confirms server connection; DEMO badge = offline mock data
2. **Alert Panel** lists LOW confidence Cowans requiring operator decision (MARK HAZARD / CONFIRM SAFE)
3. **Target Queue** shows Pass 2 waypoints — locked until all LOW alerts resolved
4. **Initiate Pass 2** button activates when all waypoints are clear
5. Scout mode replaces Target Queue with **Obstacle Profile** summary + AGL range

## Hazard Confidence Tiers

| Tier | Behavior | Example |
|------|----------|---------|
| HIGH | Auto-classified safe, no action needed | OSM-confirmed power line |
| MEDIUM | Soft alert, shown in panel, does not lock waypoints | Inferred fence line |
| LOW | Hard stop — locks all nearby waypoints until operator resolves | Tower (guy wire risk) |

## Field Deployment

```bash
cd companion_app && npm run build
uvicorn api.server:app --host 0.0.0.0 --port 8000
# Operator opens http://<LAPTOP_IP>:8000 on RC Pro browser
```

## Tests

```bash
python -m pytest tests/ -v
```

## Tech Stack

- **Python 3.12** — core processing pipeline
- **FastAPI + Uvicorn** — API server
- **React + Vite + Tailwind** — companion app
- **Leaflet** — satellite map (ESRI World Imagery + CARTO labels)
- **OpenCV + SciPy** — thermal blob detection
- **OSM Overpass API** — power line corridor verification
- **sentinel-core** — shared DJI EXIF/XMP/thermal metadata library
- **DJI WPML** — waypoint mission format for DJI Pilot 2
