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

# ── Shared Pass 2 safety constants ───────────────────────────────────────────
# These are the SINGLE source of truth for both the companion-app UI
# (api/server.py) and the KMZ actually flown (core/waypoint_generator.py).
# Any change here affects both surfaces identically — that is intentional.
MIN_SAFE_ALT_M              = 15.0  # never descend below this
SAFE_ALT_SEARCH_RADIUS_M    = 60.0  # baseline obstacle search radius
SAFE_ALT_EXTRA_MARGIN_M     = 5.0   # extra margin on top of SAFETY_BUFFER_M
WAYPOINT_APPROACH_BUFFER_M  = 20.0  # added to exclusion radius for lock checks

# DJI flight-log column names that carry a true rangefinder reading.
RANGEFINDER_COLUMNS = ('ultrasonic_height', 'OSD.ultraHeight [m]', 'rangefinder_m')


@dataclass
class Cowan:
    """A hazard or obstacle detected in the airspace."""
    lat: float
    lon: float
    height_m: float
    type: str                  # tree, building, fence_line, power_line, tower, guy_wire,
                               # water, vehicle, antenna, irrigation_pivot
    confidence: str            # HIGH, MEDIUM, LOW
    exclusion_radius_m: float  # for guy wire cones
    note: str = ''
    id: str = ''
    source: str = 'rangefinder'  # 'rangefinder' | 'visual' — preserves backward compat


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
        r.raise_for_status()  # 429/504 HTML pages surface as HTTP errors, not JSON parse noise
        return r.json().get('elements', [])
    except Exception as e:
        print(f"  OSM fetch failed: {e}")
        return []


def parse_flight_log(log_path: str, with_meta: bool = False):
    """
    Parse DJI flight log CSV for rangefinder + GPS readings.
    Expected columns: latitude, longitude, altitude, ultrasonic_height

    Parameters
    ----------
    with_meta : bool
        If True, returns (readings, meta) where meta includes
        'rangefinder_missing': True when NO known rangefinder column
        (see RANGEFINDER_COLUMNS) exists in the log.  In that case every
        reading falls back to range_m = alt, hazard_height() is 0 for all
        rows, and ZERO hazards will be detected — the caller must surface
        this degraded state to the operator instead of silently reporting
        a hazard-free property.
    """
    import csv
    readings = []
    rangefinder_missing = False
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
        fieldnames = reader.fieldnames or []
        if not any(col in fieldnames for col in RANGEFINDER_COLUMNS):
            rangefinder_missing = True
            print(
                "\n"
                "  *** WARNING: NO RANGEFINDER COLUMN FOUND IN FLIGHT LOG ***\n"
                f"  Expected one of: {', '.join(RANGEFINDER_COLUMNS)}\n"
                f"  Found columns:   {', '.join(fieldnames) or '(none)'}\n"
                "  All readings fall back to range = altitude, so hazard height\n"
                "  is ZERO for every point — NO obstacles can be detected from\n"
                "  this log.  Do NOT treat the resulting airspace as hazard-free.\n"
            )
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
    if with_meta:
        return readings, {'rangefinder_missing': rangefinder_missing}
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


def _cowan_field(cowan, name: str, default=None):
    """Read a field from either a Cowan dataclass or a plain dict.

    The API layer works with JSON dicts; the KMZ path works with Cowan
    dataclasses.  The shared safety functions below must treat both
    identically, so all field access goes through this helper.
    """
    if isinstance(cowan, dict):
        return cowan.get(name, default)
    return getattr(cowan, name, default)


def get_safe_altitude(
    lat: float,
    lon: float,
    cowans: list,
    radius_m: float = SAFE_ALT_SEARCH_RADIUS_M,
) -> float:
    """Return minimum safe Pass 2 altitude for a target coordinate.

    SINGLE SOURCE OF TRUTH for safe altitude — used by BOTH
    api/server.py (the altitude the operator sees in the companion app)
    and core/waypoint_generator.py (the executeHeight the drone flies).
    The two values must be identical; do not fork this logic.

    Rules
    -----
    - A Cowan is considered if its distance to the target is within
      max(radius_m, its own exclusion_radius_m).  Tall towers declare
      guy-wire cones of height*1.5 which can exceed the baseline search
      radius — ignoring them put waypoints at 15m inside wire cones.
    - Altitude = max obstacle height + SAFETY_BUFFER_M + SAFE_ALT_EXTRA_MARGIN_M,
      rounded, floored at MIN_SAFE_ALT_M.
    - Cowans without coordinates (e.g. visual detections with lat/lon=None)
      cannot be range-checked and are skipped here; they are handled by the
      waypoint lock rule instead.
    """
    nearby_heights = []
    for c in cowans:
        c_lat = _cowan_field(c, 'lat')
        c_lon = _cowan_field(c, 'lon')
        if c_lat is None or c_lon is None:
            continue
        exclusion_r = float(_cowan_field(c, 'exclusion_radius_m', 0.0) or 0.0)
        effective_radius = max(radius_m, exclusion_r)
        if haversine(lat, lon, c_lat, c_lon) <= effective_radius:
            nearby_heights.append(float(_cowan_field(c, 'height_m', 0.0) or 0.0))

    if not nearby_heights:
        return MIN_SAFE_ALT_M  # default if no obstacles detected nearby
    return float(max(
        MIN_SAFE_ALT_M,
        round(max(nearby_heights) + SAFETY_BUFFER_M + SAFE_ALT_EXTRA_MARGIN_M),
    ))


def get_waypoint_lock(
    lat: float,
    lon: float,
    cowans: list,
    resolutions: dict,
) -> tuple[str | None, str | None]:
    """Return (locked_by, lock_reason) for a Pass 2 waypoint position.

    SINGLE SOURCE OF TRUTH for the waypoint-lock safety gate — used by
    BOTH api/server.py (UI lock display) and core/waypoint_generator.py
    (which must EXCLUDE locked clusters from the flown KMZ).

    A waypoint is locked when any LOW-confidence Cowan whose exclusion
    zone (+ approach buffer) overlaps the position has not been resolved
    'safe' by the operator.  Obstacles resolved 'hazard' stay locked.
    """
    for c in cowans:
        if _cowan_field(c, 'confidence') != 'LOW':
            continue
        c_lat = _cowan_field(c, 'lat')
        c_lon = _cowan_field(c, 'lon')
        if c_lat is None or c_lon is None:
            continue  # cannot range-check un-localised detections
        exclusion_r = float(_cowan_field(c, 'exclusion_radius_m', 0.0) or 0.0)
        dist = haversine(lat, lon, c_lat, c_lon)
        if dist < exclusion_r + WAYPOINT_APPROACH_BUFFER_M:
            c_id = _cowan_field(c, 'id', '')
            decision = (resolutions or {}).get(c_id)
            if decision != 'safe':
                reason = 'Confirmed hazard' if decision == 'hazard' else 'Unresolved'
                return c_id, f"{reason} obstacle nearby ({c_id})"
    return None, None


def merge_visual_cowans(
    rangefinder_cowans: list[Cowan],
    visual_cowans: list[dict],
) -> list[Cowan]:
    """
    Merge visual detector output into the rangefinder Cowan list.

    Strategy
    --------
    - Each visual_cowan dict is converted to a Cowan dataclass.
    - lat/lon: borrowed from the nearest rangefinder cowan of ANY type if one
      exists within 50m (proxy for "same area"); otherwise 0.0.
    - Deduplication: if a visual cowan and a rangefinder cowan share the same
      type and are within 15m, the rangefinder entry wins (higher positional
      accuracy) and the visual duplicate is discarded.

    Parameters
    ----------
    rangefinder_cowans : list[Cowan]
        Obstacles already identified by identify_cowans() from telemetry + OSM.
    visual_cowans : list[dict]
        Cowan-format dicts returned by visual_detector.detect_from_folder().
        May have lat=None / lon=None.

    Returns
    -------
    list[Cowan]
        Merged and deduplicated obstacle list.
    """
    if not visual_cowans:
        return rangefinder_cowans

    DEDUP_RADIUS_M = 15.0   # same-type dedup threshold

    merged = list(rangefinder_cowans)  # start with rangefinder as canonical

    for v_idx, vd in enumerate(visual_cowans):
        # ── Resolve lat/lon ──────────────────────────────────────────────────
        v_lat = vd.get('lat')
        v_lon = vd.get('lon')

        if v_lat is None or v_lon is None:
            # Borrow GPS from the property centroid of rangefinder cowans.
            # Visual detections carry no GPS — use the median lat/lon of all
            # rangefinder obstacles as a reasonable property-centre proxy.
            if rangefinder_cowans:
                import statistics
                v_lat = statistics.median(rc.lat for rc in rangefinder_cowans)
                v_lon = statistics.median(rc.lon for rc in rangefinder_cowans)
            else:
                v_lat = 0.0
                v_lon = 0.0

        v_lat = float(v_lat)
        v_lon = float(v_lon)

        # ── Deduplication against rangefinder cowans ─────────────────────────
        duplicate = False
        for rc in rangefinder_cowans:
            if rc.type != vd.get('type'):
                continue
            dist = haversine(v_lat, v_lon, rc.lat, rc.lon)
            if dist <= DEDUP_RADIUS_M:
                duplicate = True
                break

        if duplicate:
            continue  # rangefinder entry kept; visual duplicate discarded

        # ── Convert to Cowan and append ──────────────────────────────────────
        new_cowan = Cowan(
            id=vd.get('id', f'vis_{vd.get("type", "unknown")}_{v_idx}'),
            lat=v_lat,
            lon=v_lon,
            height_m=float(vd.get('height_m') or 0.0),
            type=vd.get('type', 'unknown'),
            confidence=vd.get('confidence', 'LOW'),
            exclusion_radius_m=float(vd.get('exclusion_radius_m', 10.0)),
            note=vd.get('note', ''),
            source='visual',
        )
        merged.append(new_cowan)

    return merged


def tile_airspace(
    log_path: str,
    output_dir: str,
    bounds: Optional[dict] = None,
    visual_detections: list[dict] | None = None,
):
    """
    Tiles the mission airspace by identifying hazards and saving a security map.

    Parameters
    ----------
    log_path : str
        Path to DJI flight log CSV.
    output_dir : str
        Directory where the tiled airspace JSON is written.
    bounds : dict | None
        Optional bounding box for OSM power-line lookup.
    visual_detections : list[dict] | None
        Optional Cowan-format dicts from visual_detector.detect_from_folder().
        If provided, they are merged (with deduplication) into the rangefinder
        cowans before the security map is written.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print(f"The Outer Guard is scanning flight log: {log_path}")
    readings, log_meta = parse_flight_log(log_path, with_meta=True)
    print(f"  {len(readings)} telemetry points received")
    rangefinder_missing = log_meta['rangefinder_missing']

    osm_lines = []
    if bounds:
        print("Consulting OSM for utility corridor confirmation...")
        osm_lines = fetch_osm_power_lines(bounds)
        print(f"  {len(osm_lines)} OSM records integrated")

    cowans = identify_cowans(readings, osm_lines)

    # ── Visual layer integration ─────────────────────────────────────────────
    if visual_detections:
        before = len(cowans)
        cowans = merge_visual_cowans(cowans, visual_detections)
        added  = len(cowans) - before
        print(f"  Visual layer: {len(visual_detections)} detections merged, {added} new cowans added")

    mission_id = Path(log_path).stem
    out_file = output_path / f"{mission_id}_tiled_airspace.json"
    with open(out_file, 'w') as f:
        json.dump({
            'rangefinder_missing': rangefinder_missing,
            'cowans': [asdict(c) for c in cowans],
        }, f, indent=2)

    high = sum(1 for c in cowans if c.confidence == 'HIGH')
    med  = sum(1 for c in cowans if c.confidence == 'MEDIUM')
    low  = sum(1 for c in cowans if c.confidence == 'LOW')
    vis  = sum(1 for c in cowans if c.source == 'visual')
    print(
        f"Airspace Tiled: {len(cowans)} hazards (Cowans) identified -> "
        f"HIGH:{high} MEDIUM:{med} LOW:{low}  "
        f"(rangefinder:{len(cowans)-vis} visual:{vis})"
    )
    if rangefinder_missing:
        print(
            "  *** DEGRADED RESULT: rangefinder data missing from flight log — "
            "the hazard count above reflects visual/OSM sources only. ***"
        )
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
