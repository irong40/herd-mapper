"""
The Outer Guard: rangefinder telemetry + OSM -> property obstacle profile

Identifies 'cowans and eavesdroppers' (hazards like power lines, towers, and fences)
to ensure the airspace is 'duly tiled' for Pass 2 autonomous flight.

Input:  DJI flight log CSV (rangefinder altitude, GPS per frame)
Output: Tiled airspace JSON with classified hazards and confidence tiers
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
TOWER_HEIGHT_MIN_M = 15       # above this + narrow profile -> probable tower
MIN_PATTERN_POLES = 3         # need at least 3 to confirm a line
SAFETY_BUFFER_M = 8           # added to obstacle height for Pass 2 altitude


@dataclass
class Cowan:
    """A hazard or obstacle detected in the airspace."""
    lat: float
    lon: float
    height_m: float
    type: str                  # tree, building, fence_line, power_line, tower, unknown
    confidence: str            # HIGH, MEDIUM, LOW
    exclusion_radius_m: float  # for guy wire cones
    note: str = ''
    id: str = ''


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
    Expected columns: latitude, longitude, altitude, ultrasonic_height
    """
    import csv
    readings = []
    with open(log_path, encoding='utf-8', errors='ignore') as f:
        # Some DJI logs have a header skip or different encodings
        content = f.read()
        if 'latitude' not in content.lower():
            # Handle potential metadata lines at start of some DJI CSV exports
            lines = content.splitlines()
            for i, line in enumerate(lines):
                if 'latitude' in line.lower():
                    content = '\n'.join(lines[i:])
                    break
        
        from io import StringIO
        reader = csv.DictReader(StringIO(content))
        for row in reader:
            try:
                # Map standard DJI log columns
                lat = float(row.get('latitude') or row.get('OSD.latitude') or 0)
                lon = float(row.get('longitude') or row.get('OSD.longitude') or 0)
                alt = float(row.get('altitude') or row.get('OSD.height [m]') or 0)
                # ultrasonic_height is usually rangefinder
                range_m = float(row.get('ultrasonic_height') or row.get('OSD.ultraHeight [m]') or row.get('rangefinder_m') or alt)
                
                if lat != 0 and lon != 0:
                    readings.append({
                        'lat': lat,
                        'lon': lon,
                        'drone_alt_m': alt,
                        'rangefinder_m': range_m,
                    })
            except (KeyError, ValueError):
                continue
    return readings


def hazard_height(drone_alt_m: float, rangefinder_m: float) -> float:
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


def identify_cowans(readings: list[dict], osm_lines: list[dict]) -> list[Cowan]:
    cowans = []

    osm_coords = set()
    for way in osm_lines:
        if 'geometry' in way:
            for node in way['geometry']:
                osm_coords.add((round(node['lat'], 4), round(node['lon'], 4)))

    elevated = [
        {**r, 'height_m': hazard_height(r['drone_alt_m'], r['rangefinder_m'])}
        for r in readings
        if hazard_height(r['drone_alt_m'], r['rangefinder_m']) > 1.0
    ]

    # Towers: tall + isolated
    towers = [e for e in elevated if e['height_m'] >= TOWER_HEIGHT_MIN_M]
    for t_idx, t in enumerate(towers):
        cone_r = t['height_m'] * GUY_WIRE_CONE_FACTOR
        cowans.append(Cowan(
            id=f'tower_{t_idx}',
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

    for p_idx, pattern in enumerate(patterns):
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

        for q_idx, p in enumerate(pattern):
            cowans.append(Cowan(
                id=f'{obs_type}_{p_idx}_{q_idx}',
                lat=p['lat'], lon=p['lon'],
                height_m=p['height_m'] + SAFETY_BUFFER_M,
                type=obs_type,
                confidence=confidence,
                exclusion_radius_m=5.0,
                note='OSM confirmed' if osm_match else 'Pattern inferred'
            ))

    return cowans


def get_safe_altitude(lat: float, lon: float, cowans: list[Cowan], radius_m: float = 50) -> float:
    """Return minimum safe Pass 2 altitude for a target coordinate."""
    nearby = [
        c for c in cowans
        if haversine(lat, lon, c.lat, c.lon) <= radius_m
    ]
    if not nearby:
        return 15.0  # default 15m if no obstacles detected nearby
    return max(c.height_m for c in nearby) + SAFETY_BUFFER_M


def tile_airspace(log_path: str, output_dir: str, bounds: Optional[dict] = None):
    """
    Tiles the mission airspace by identifying hazards and saving a security map.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"The Outer Guard is scanning flight log: {log_path}")
    readings = parse_flight_log(log_path)
    print(f"  {len(readings)} telemetry points received")

    osm_lines = []
    if bounds:
        print("Consulting OSM for utility corridor confirmation...")
        osm_lines = fetch_osm_power_lines(bounds)
        print(f"  {len(osm_lines)} OSM records integrated")

    cowans = identify_cowans(readings, osm_lines)

    mission_id = Path(log_path).stem
    out_file = output_path / f"{mission_id}_tiled_airspace.json"
    with open(out_file, 'w') as f:
        json.dump([asdict(c) for c in cowans], f, indent=2)

    high = sum(1 for c in cowans if c.confidence == 'HIGH')
    med = sum(1 for c in cowans if c.confidence == 'MEDIUM')
    low = sum(1 for c in cowans if c.confidence == 'LOW')
    print(f"Airspace Tiled: {len(cowans)} hazards (Cowans) identified -> HIGH:{high} MEDIUM:{med} LOW:{low}")
    print(f"Security map saved to {out_file}")
    return cowans


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='The Outer Guard: Tiling Airspace for Safe Flight')
    parser.add_argument('--log', required=True, help='DJI flight log CSV path')
    parser.add_argument('--output', required=True, help='Output directory')
    parser.add_argument('--bounds', help='JSON string: {"north":..,"south":..,"east":..,"west":..}')
    args = parser.parse_args()
    bounds = json.loads(args.bounds) if args.bounds else None
    tile_airspace(args.log, args.output, bounds)
