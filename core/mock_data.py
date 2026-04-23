"""
Demo mock data generator — simulates a complete Pass 1 result for a 50-acre property.

Generates:
  - data/detections/demo_detections.json   (deer clusters near lake)
  - data/obstacles/demo_obstacles.json     (fence, power line, tower)
  - data/missions/demo/bounds.json         (property boundary for map)

Usage:
    python core/mock_data.py
"""

import json
import math
from pathlib import Path

# Property center — rural Chesapeake VA area
CENTER_LAT = 36.7821
CENTER_LON = -76.4523

# 50 acres ≈ 450m x 450m
HALF_M = 225
DEG_PER_M_LAT = 1 / 111320
DEG_PER_M_LON = 1 / (111320 * math.cos(math.radians(CENTER_LAT)))


def offset(lat, lon, dx_m, dy_m):
    return (
        lat + dy_m * DEG_PER_M_LAT,
        lon + dx_m * DEG_PER_M_LON,
    )


def generate():
    out_detections = Path('data/detections')
    out_obstacles = Path('data/obstacles')
    out_missions = Path('data/missions/demo')
    for p in [out_detections, out_obstacles, out_missions]:
        p.mkdir(parents=True, exist_ok=True)

    # ── Property bounds ──────────────────────────────────────────────────────
    north_lat, _ = offset(CENTER_LAT, CENTER_LON, 0, HALF_M)
    south_lat, _ = offset(CENTER_LAT, CENTER_LON, 0, -HALF_M)
    _, east_lon = offset(CENTER_LAT, CENTER_LON, HALF_M, 0)
    _, west_lon = offset(CENTER_LAT, CENTER_LON, -HALF_M, 0)

    bounds = {
        'north': north_lat, 'south': south_lat,
        'east': east_lon,   'west': west_lon,
        'center_lat': CENTER_LAT, 'center_lon': CENTER_LON,
        'name': 'Demo Property — 50 acres',
    }
    with open(out_missions / 'bounds.json', 'w') as f:
        json.dump(bounds, f, indent=2)

    # ── Lake polygon (SW quadrant) ───────────────────────────────────────────
    lake_center = offset(CENTER_LAT, CENTER_LON, -120, -100)
    lake = {
        'center_lat': lake_center[0],
        'center_lon': lake_center[1],
        'radius_m': 45,
        'label': 'Pond',
    }
    with open(out_missions / 'lake.json', 'w') as f:
        json.dump(lake, f, indent=2)

    # ── Deer clusters ────────────────────────────────────────────────────────
    clusters = [
        {
            'id': 'cluster_001',
            'lat': offset(CENTER_LAT, CENTER_LON, -90, -80)[0],
            'lon': offset(CENTER_LAT, CENTER_LON, -90, -80)[1],
            'count': 8,
            'confidence': 'HIGH',
            'label': 'Herd near pond edge',
            'source_images': ['DJI_20260423_054312_0041_T.JPG', 'DJI_20260423_054318_0042_T.JPG'],
        },
        {
            'id': 'cluster_002',
            'lat': offset(CENTER_LAT, CENTER_LON, -140, -120)[0],
            'lon': offset(CENTER_LAT, CENTER_LON, -140, -120)[1],
            'count': 7,
            'confidence': 'HIGH',
            'label': 'Bedded group — pond NW',
            'source_images': ['DJI_20260423_054401_0048_T.JPG'],
        },
        {
            'id': 'cluster_003',
            'lat': offset(CENTER_LAT, CENTER_LON, 60, -50)[0],
            'lon': offset(CENTER_LAT, CENTER_LON, 60, -50)[1],
            'count': 3,
            'confidence': 'MEDIUM',
            'label': 'Possible deer — field center',
            'source_images': ['DJI_20260423_054512_0057_T.JPG'],
        },
        {
            'id': 'cluster_004',
            'lat': offset(CENTER_LAT, CENTER_LON, 150, 80)[0],
            'lon': offset(CENTER_LAT, CENTER_LON, 150, 80)[1],
            'count': 2,
            'confidence': 'MEDIUM',
            'label': 'Unverified — tree line edge',
            'source_images': ['DJI_20260423_054603_0064_T.JPG'],
        },
    ]

    detections = {
        'mission_id': 'demo',
        'pass1_agl_ft': 200,
        'total_blobs': 22,
        'clusters': clusters,
    }
    with open(out_detections / 'demo_detections.json', 'w') as f:
        json.dump(detections, f, indent=2)

    # ── Obstacles ────────────────────────────────────────────────────────────
    obstacles = []

    # Fence — north boundary (post pattern)
    fence_north_y = HALF_M - 20
    for dx in range(-200, 210, 12):
        lat, lon = offset(CENTER_LAT, CENTER_LON, dx, fence_north_y)
        obstacles.append({
            'id': f'fence_n_{dx}',
            'lat': lat, 'lon': lon,
            'height_m': 6.0,
            'type': 'fence_line',
            'confidence': 'MEDIUM',
            'exclusion_radius_m': 4.0,
            'note': 'Post pattern inferred — north boundary',
        })

    # Fence — east boundary
    fence_east_x = HALF_M - 20
    for dy in range(-200, 210, 12):
        lat, lon = offset(CENTER_LAT, CENTER_LON, fence_east_x, dy)
        obstacles.append({
            'id': f'fence_e_{dy}',
            'lat': lat, 'lon': lon,
            'height_m': 6.0,
            'type': 'fence_line',
            'confidence': 'MEDIUM',
            'exclusion_radius_m': 4.0,
            'note': 'Post pattern inferred — east boundary',
        })

    # Power line — diagonal NW to SE
    for i, t in enumerate([x / 10 for x in range(0, 11)]):
        dx = -180 + t * 360
        dy = 160 - t * 320
        lat, lon = offset(CENTER_LAT, CENTER_LON, dx, dy)
        obstacles.append({
            'id': f'powerline_{i}',
            'lat': lat, 'lon': lon,
            'height_m': 14.0,
            'type': 'power_line',
            'confidence': 'HIGH',
            'exclusion_radius_m': 8.0,
            'note': 'OSM confirmed — utility corridor',
        })

    # Tower — NE corner with guy wire exclusion cone
    tower_lat, tower_lon = offset(CENTER_LAT, CENTER_LON, 160, 140)
    tower_height = 28.0
    obstacles.append({
        'id': 'tower_001',
        'lat': tower_lat, 'lon': tower_lon,
        'height_m': tower_height,
        'type': 'tower',
        'confidence': 'LOW',
        'exclusion_radius_m': tower_height * 1.5,
        'note': 'Unidentified structure — possible comms tower. GUY WIRE HAZARD. Operator confirm required.',
    })

    with open(out_obstacles / 'demo_obstacles.json', 'w') as f:
        json.dump(obstacles, f, indent=2)

    print("Demo data generated:")
    print(f"  {len(clusters)} deer clusters ({sum(c['count'] for c in clusters)} animals)")
    print(f"  {len(obstacles)} obstacle points")
    print(f"  Property bounds: {south_lat:.4f}–{north_lat:.4f}N, {west_lon:.4f}–{east_lon:.4f}W")
    print()
    print("Load companion app and point it at data/")


if __name__ == '__main__':
    generate()
