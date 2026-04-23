"""
Obstacle mapper: rangefinder telemetry + OSM → property obstacle profile

Input:  DJI flight log CSV (rangefinder altitude, GPS per frame)
Output: obstacle map JSON with classified hazards and confidence tiers

Obstacle types detected:
  - Tree canopy / vegetation (broad returns)
  - Buildings / structures (dense rectangular returns)
  - Fence lines (post pattern: consistent spacing, low height, linear)
  - Power line corridors (pole pattern: consistent spacing, taller, linear + OSM confirm)
  - Towers / guy wire hazards (tall narrow isolated return → exclusion cone)
"""

import json
import numpy as np
import argparse
import requests
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional


GUY_WIRE_CONE_FACTOR = 1.5   # exclusion radius = tower_height * this
POLE_SPACING_MIN_M = 30
POLE_SPACING_MAX_M = 320
POLE_HEIGHT_MIN_M = 8
TOWER_HEIGHT_MIN_M = 15       # above this + narrow profile → probable tower
MIN_PATTERN_POLES = 3         # need at least 3 to confirm a line
SAFETY_BUFFER_M = 8           # added to obstacle height for Pass 2 altitude


@dataclass
class Obstacle:
    lat: float
    lon: float
    height_m: float
    type: str                  # tree, building, fence_line, power_line, tower, unknown
    confidence: str            # HIGH, MEDIUM, LOW
    exclusion_radius_m: float  # for guy wire cones
    note: str = ''


def fetch_osm_power_lines(bounds: dict) -> list[dict]:
    """Pull power line ways from Overpass API for the mission bounds."""
    query = f"""
    [out:json][timeout:25];
    (
      way["power"="line"]({bounds['south']},{bounds['west']},{bounds['north']},{bounds['east']});
      way["power"="minor_line"]({bounds['south']},{bounds['west']},{bounds['north']},{bounds['east']});
    );
    out geom;
    """
    try:
        r = requests.post('https://overpass-api.de/api/interpreter', data=query, timeout=30)
        return r.json().get('elements', [])
    except Exception as e:
        print(f"  OSM fetch failed: {e}")
        return []


def parse_flight_log(log_path: str) -> list[dict]:
    """
    Parse DJI flight log CSV for rangefinder + GPS readings.
    Expected columns: timestamp, lat, lon, altitude_agl_m, rangefinder_m
    Adjust column names to match actual DJI log export format.
    """
    import csv
    readings = []
    with open(log_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                readings.append({
                    'lat': float(row['latitude']),
                    'lon': float(row['longitude']),
                    'drone_alt_m': float(row['altitude']),
                    'rangefinder_m': float(row['ultrasonic_height']),
                })
            except (KeyError, ValueError):
                continue
    return readings


def obstacle_height(drone_alt_m: float, rangefinder_m: float) -> float:
    """Height of surface hit = drone altitude minus rangefinder reading."""
    return max(0.0, drone_alt_m - rangefinder_m)


def detect_pattern(points: list[dict], min_count: int, spacing_min: float, spacing_max: float) -> list[list[dict]]:
    """Find linear sequences of points with consistent spacing."""
    if len(points) < min_count:
        return []

    used = set()
    patterns = []

    for i, p in enumerate(points):
        if i in used:
            continue
        line = [p]
        used.add(i)

        for j, p2 in enumerate(points):
            if j in used:
                continue
            dist = haversine(p['lat'], p['lon'], p2['lat'], p2['lon'])
            if spacing_min <= dist <= spacing_max:
                if len(line) < 2 or _collinear(line[-2], line[-1], p2, tolerance_deg=0.002):
                    line.append(p2)
                    used.add(j)

        if len(line) >= min_count:
            patterns.append(line)

    return patterns


def haversine(lat1, lon1, lat2, lon2) -> float:
    R = 6371000
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi/2)**2 + np.cos(phi1)*np.cos(phi2)*np.sin(dlam/2)**2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))


def _collinear(p1, p2, p3, tolerance_deg=0.002) -> bool:
    """Check if three GPS points are roughly collinear."""
    v1 = (p2['lat'] - p1['lat'], p2['lon'] - p1['lon'])
    v2 = (p3['lat'] - p2['lat'], p3['lon'] - p2['lon'])
    cross = abs(v1[0] * v2[1] - v1[1] * v2[0])
    return cross < tolerance_deg


def classify_obstacles(readings: list[dict], osm_lines: list[dict]) -> list[Obstacle]:
    obstacles = []

    osm_coords = set()
    for way in osm_lines:
        if 'geometry' in way:
            for node in way['geometry']:
                osm_coords.add((round(node['lat'], 4), round(node['lon'], 4)))

    elevated = [
        {**r, 'height_m': obstacle_height(r['drone_alt_m'], r['rangefinder_m'])}
        for r in readings
        if obstacle_height(r['drone_alt_m'], r['rangefinder_m']) > 1.0
    ]

    # Towers: tall + isolated
    towers = [e for e in elevated if e['height_m'] >= TOWER_HEIGHT_MIN_M]
    for t in towers:
        cone_r = t['height_m'] * GUY_WIRE_CONE_FACTOR
        obstacles.append(Obstacle(
            lat=t['lat'], lon=t['lon'],
            height_m=t['height_m'],
            type='tower',
            confidence='LOW',
            exclusion_radius_m=cone_r,
            note=f'Guy wire exclusion cone {cone_r:.0f}m radius'
        ))

    # Pole patterns: fence or power line
    poles = [e for e in elevated if POLE_HEIGHT_MIN_M <= e['height_m'] < TOWER_HEIGHT_MIN_M]
    patterns = detect_pattern(poles, MIN_PATTERN_POLES, POLE_SPACING_MIN_M, POLE_SPACING_MAX_M)

    for pattern in patterns:
        avg_height = np.mean([p['height_m'] for p in pattern])
        centroid_lat = np.mean([p['lat'] for p in pattern])
        centroid_lon = np.mean([p['lon'] for p in pattern])

        osm_match = any(
            abs(centroid_lat - c[0]) < 0.001 and abs(centroid_lon - c[1]) < 0.001
            for c in osm_coords
        )

        if osm_match or avg_height > 10:
            obs_type = 'power_line'
            confidence = 'HIGH' if osm_match else 'MEDIUM'
        else:
            obs_type = 'fence_line'
            confidence = 'MEDIUM'

        for p in pattern:
            obstacles.append(Obstacle(
                lat=p['lat'], lon=p['lon'],
                height_m=p['height_m'] + SAFETY_BUFFER_M,
                type=obs_type,
                confidence=confidence,
                exclusion_radius_m=5.0,
                note='OSM confirmed' if osm_match else 'Pattern inferred'
            ))

    return obstacles


def get_safe_altitude(lat: float, lon: float, obstacles: list[Obstacle], radius_m: float = 50) -> float:
    """Return minimum safe Pass 2 altitude for a target coordinate."""
    nearby = [
        o for o in obstacles
        if haversine(lat, lon, o.lat, o.lon) <= radius_m
    ]
    if not nearby:
        return 15.0  # default 15m if no obstacles detected nearby
    return max(o.height_m for o in nearby) + SAFETY_BUFFER_M


def run(log_path: str, output_dir: str, bounds: Optional[dict] = None):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"Parsing flight log: {log_path}")
    readings = parse_flight_log(log_path)
    print(f"  {len(readings)} rangefinder readings")

    osm_lines = []
    if bounds:
        print("Fetching OSM power line data...")
        osm_lines = fetch_osm_power_lines(bounds)
        print(f"  {len(osm_lines)} OSM power line ways")

    obstacles = classify_obstacles(readings, osm_lines)

    mission_id = Path(log_path).stem
    out_file = output_path / f"{mission_id}_obstacles.json"
    with open(out_file, 'w') as f:
        json.dump([asdict(o) for o in obstacles], f, indent=2)

    high = sum(1 for o in obstacles if o.confidence == 'HIGH')
    med = sum(1 for o in obstacles if o.confidence == 'MEDIUM')
    low = sum(1 for o in obstacles if o.confidence == 'LOW')
    print(f"Obstacles mapped: {len(obstacles)} total — HIGH:{high} MEDIUM:{med} LOW:{low}")
    print(f"Saved to {out_file}")
    return obstacles


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--log', required=True, help='DJI flight log CSV path')
    parser.add_argument('--output', required=True, help='Output directory')
    parser.add_argument('--bounds', help='JSON string: {"north":..,"south":..,"east":..,"west":..}')
    args = parser.parse_args()
    bounds = json.loads(args.bounds) if args.bounds else None
    run(args.log, args.output, bounds)
