# Herd Mapper

Adaptive two-pass wildlife census system for SAI. M4T drone flies a thermal grid (Pass 1), detects animal clusters, builds an obstacle map, then autonomously routes to flagged areas for dual-capture investigation (Pass 2). MVP uses two sorties with ground processing between passes. Architecture is designed to slot Manifold 3 onboard later with no structural changes.

## Current Phase
**Phase 1 MVP** — two-sortie, ground processing, deer census on M4T

## Stack
- **Core processing**: Python 3.12
- **Companion app**: React + Vite (web app, runs in RC Pro browser, displays on wireless HDMI monitor)
- **Database**: Supabase (mission logs, detections, obstacle maps)
- **Species detection**: Wildlife Insights API (deer primary)
- **Obstacle data**: OSM Overpass API (power lines, structures)
- **Report output**: SAI Report Builder integration
- **Future**: DJI PSDK 3.15.0 + Manifold 3 for onboard single-mission mode

## Project Structure
```
core/
  blob_detector.py        # Thermal image → deer cluster GPS coords
  obstacle_mapper.py      # Rangefinder data → obstacle profile + pattern inference
  waypoint_generator.py   # Blob targets + safe altitudes → KMZ for DJI Pilot 2
  osm_fetcher.py          # Fetch power lines / structures from Overpass API
  species_classifier.py   # Wildlife Insights API wrapper
  report_generator.py     # SAI Report Builder integration

companion_app/            # React web app
  src/
    Map.jsx               # Live property map with obstacle overlay
    AlertPanel.jsx        # Confidence-tiered detection alerts
    TargetQueue.jsx        # Pass 2 waypoints — locked/unlocked status

data/
  missions/               # Per-mission folders (GPS bounds, KMZ files)
  obstacles/              # Built obstacle maps (JSON)
  detections/             # Thermal + RGB image pairs with tags

docs/                     # ADRs and architecture notes
tests/
```

## Key Design Decisions
- Two-sortie MVP first, Manifold 3 single-mission later — same codebase, different execution mode
- Pass 1: 200ft AGL thermal grid, 70% overlap, rangefinder running throughout
- Pass 2: dynamic waypoints, altitude = max obstacle height in 50ft radius + 25ft buffer
- Obstacle confidence tiers: HIGH (auto), MEDIUM (soft alert), LOW (hard stop, operator confirm)
- Guy wire handling: tower detected → 1.5x height exclusion cone, no-fly
- Companion app is a web app — runs in DJI RC Pro browser, displays on wireless HDMI monitor
- Species: deer primary, general wildlife secondary
- Image output: thermal + RGB pair, GPS-embedded, confidence score, "unidentified" tag if below threshold

## Thermal Window (from TTPs)
- Pre-dawn optimal (1-2 hrs before sunrise)
- Wind under 10 mph
- Avoid post-rain (ground warm, deer blend)
- Temp differential: deer at 98.6°F vs ground ideally 20°F+ cooler

## Running
```bash
# After Pass 1 images downloaded from M4T:
python core/blob_detector.py --mission data/missions/MISSION_ID --output data/detections/

# Generate Pass 2 waypoints:
python core/waypoint_generator.py --detections data/detections/MISSION_ID --obstacles data/obstacles/MISSION_ID --output data/missions/MISSION_ID/pass2.kmz

# Companion app:
cd companion_app && npm run dev
```
