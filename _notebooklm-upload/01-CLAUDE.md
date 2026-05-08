# Herd Mapper

Adaptive two-pass wildlife census system for SAI. M4T drone flies a thermal grid (Pass 1), detects animal clusters, tiles the airspace for hazards (The Outer Guard), then autonomously routes to flagged areas for dual-capture investigation (Pass 2).

## Current Phase
**Phase 1 MVP** — two-sortie, ground processing, deer census on M4T/M4E

## Stack
- **Core processing**: Python 3.12
- **The Outer Guard**: Hazard mapping & airspace tiling (rangefinder + OSM)
- **Companion app**: React + Vite (web app, runs in RC Pro browser)
- **Database**: Supabase (mission logs, detections, tiled airspace)
- **Species detection**: Wildlife Insights API (deer primary)
- **Obstacle data**: OSM Overpass API (power lines, structures)
- **Report output**: SAI Report Builder integration
- **Future**: DJI PSDK 3.15.0 + Manifold 3 for onboard single-mission mode

## Project Structure
```
core/
  blob_detector.py        # Thermal image -> deer cluster GPS coords
  outer_guard.py          # The Outer Guard: Tiling airspace (identify Cowans)
  waypoint_generator.py   # Pass 2 routing using tiled airspace data (Cowans)
  osm_fetcher.py          # Fetch power lines / structures from Overpass API
  species_classifier.py   # Wildlife Insights API wrapper
  report_generator.py     # SAI Report Builder integration

companion_app/            # React web app
  src/
    Map.jsx               # Live property map with Cowan overlay
    AlertPanel.jsx        # Confidence-tiered hazard alerts
    TargetQueue.jsx        # Pass 2 waypoints — locked/unlocked status

data/
  missions/               # Per-mission folders (GPS bounds, KMZ files, logs)
  obstacles/              # Tiled airspace data (Cowans)
  detections/             # Thermal + RGB image pairs with tags

docs/                     # ADRs and architecture notes
tests/
```

## The Outer Guard (Terminology)
- **Tiling**: The process of scanning and securing a mission area for safe flight.
- **Cowan**: A hazard or obstacle (power lines, towers, etc.) that must be guarded against.
- **Duly Tiled**: An airspace that has been fully mapped and cleared for autonomous Pass 2 flight.

## Running
```bash
# After Pass 1 images/logs downloaded:
# 1. Tile the airspace (identify Cowans)
python core/outer_guard.py --log data/missions/MISSION_ID/flight_log.csv --output data/obstacles/

# 2. Detect animal clusters
python core/blob_detector.py --mission data/missions/MISSION_ID --output data/detections/

# 3. Generate Pass 2 waypoints (using Cowans for safe altitudes)
python core/waypoint_generator.py --detections data/detections/MISSION_ID_detections.json --obstacles data/obstacles/MISSION_ID_tiled_airspace.json --output data/missions/MISSION_ID/pass2.kmz

# 4. Launch Companion App
cd companion_app && npm run dev
```
