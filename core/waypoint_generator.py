"""
Waypoint generator: detection clusters + tiled airspace -> Pass 2 KMZ

For each detected cluster, calculates safe descent altitude and generates
a DJI Pilot 2 compatible KMZ waypoint file.

Usage:
    python core/waypoint_generator.py \
        --detections data/detections/MISSION_ID_detections.json \
        --obstacles data/obstacles/MISSION_ID_tiled_airspace.json \
        --output data/missions/MISSION_ID/pass2.kmz
"""

import json
import argparse
import math
import zipfile
import io
from pathlib import Path
from core.outer_guard import get_safe_altitude, Cowan
from sentinel_core.spatial import parse_kml, kml_bbox, METERS_PER_LAT_DEG


INVESTIGATION_SPEED_MS = 3.0    # m/s — slow for careful imaging
HOVER_SECONDS = 3               # pause at each target for dual capture
MIN_INVESTIGATION_ALT_M = 15    # never descend below this regardless of obstacles

# M4T thermal sensor (640×512, ~45° HFOV) swath width at given altitude
_M4T_HFOV_DEG = 45.0


def load_cowans(path: str) -> list[Cowan]:
    with open(path) as f:
        data = json.load(f)
    return [Cowan(**o) for o in data]


def build_kml(clusters: list[dict], cowans: list[Cowan]) -> str:
    waypoints = []

    for i, cluster in enumerate(clusters):
        safe_alt = max(
            get_safe_altitude(cluster['lat'], cluster['lon'], cowans),
            MIN_INVESTIGATION_ALT_M
        )

        waypoints.append({
            'index': i,
            'lat': cluster['lat'],
            'lon': cluster['lon'],
            'alt_m': safe_alt,
            'count': cluster['count'],
            'confidence': cluster['confidence'],
        })

    kml = ['<?xml version="1.0" encoding="UTF-8"?>']
    kml.append('<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:wpml="http://www.dji.com/wpmz/1.0.6">')
    kml.append('<Document>')
    kml.append('<wpml:missionConfig>')
    kml.append(f'  <wpml:flyToWaylineMode>safely</wpml:flyToWaylineMode>')
    kml.append(f'  <wpml:finishAction>goHome</wpml:finishAction>')
    kml.append(f'  <wpml:exitOnRCLost>goBack</wpml:exitOnRCLost>')
    kml.append('</wpml:missionConfig>')
    kml.append('<Folder>')
    kml.append('<wpml:templateType>waypoint</wpml:templateType>')

    for wp in waypoints:
        kml.append(f'<Placemark>')
        kml.append(f'  <Point><coordinates>{wp["lon"]},{wp["lat"]},{wp["alt_m"]}</coordinates></Point>')
        kml.append(f'  <wpml:index>{wp["index"]}</wpml:index>')
        kml.append(f'  <wpml:executeHeight>{wp["alt_m"]:.1f}</wpml:executeHeight>')
        kml.append(f'  <wpml:waypointSpeed>{INVESTIGATION_SPEED_MS}</wpml:waypointSpeed>')
        kml.append(f'  <wpml:waypointHeadingParam>')
        kml.append(f'    <wpml:waypointHeadingMode>smoothTransition</wpml:waypointHeadingMode>')
        kml.append(f'  </wpml:waypointHeadingParam>')
        kml.append(f'  <wpml:waypointTurnParam>')
        kml.append(f'    <wpml:waypointTurnMode>toPointAndStopWithDiscontinuityCurvature</wpml:waypointTurnMode>')
        kml.append(f'  </wpml:waypointTurnParam>')
        kml.append(f'  <wpml:actionGroup>')
        kml.append(f'    <wpml:action><wpml:actionActuatorFunc>takePhoto</wpml:actionActuatorFunc></wpml:action>')
        kml.append(f'    <wpml:action><wpml:actionActuatorFunc>hover</wpml:actionActuatorFunc>'
                   f'<wpml:actionActuatorFuncParam><wpml:hoverTime>{HOVER_SECONDS}</wpml:hoverTime>'
                   f'</wpml:actionActuatorFuncParam></wpml:action>')
        kml.append(f'  </wpml:actionGroup>')
        kml.append(f'  <!-- cluster_count:{wp["count"]} confidence:{wp["confidence"]} -->')
        kml.append(f'</Placemark>')

    kml.append('</Folder>')
    kml.append('</Document>')
    kml.append('</kml>')
    return '\n'.join(kml)


def generate_pass1_grid(
    kml_path: str,
    altitude_m: float = 60.0,
    speed_ms: float = 5.0,
    overlap_pct: float = 0.75,
    output_path: str = None,
) -> bytes:
    """Generate a Pass 1 thermal grid KMZ from a property boundary KML.

    Loads the first polygon from kml_path, computes a lawnmower grid within
    its bounding box at altitude_m, and returns the KMZ bytes.  Writes to
    output_path if provided.
    """
    kml_data = parse_kml(kml_path)
    if not kml_data["polygons"]:
        raise ValueError(f"No polygons found in {kml_path}")
    polygon = kml_data["polygons"][0]
    min_lat, max_lat, min_lon, max_lon = kml_bbox(polygon)

    # Swath width and row spacing
    swath_m = 2 * altitude_m * math.tan(math.radians(_M4T_HFOV_DEG / 2))
    row_spacing_m = swath_m * (1.0 - overlap_pct)

    center_lat = (min_lat + max_lat) / 2.0
    m_per_lon = METERS_PER_LAT_DEG * math.cos(math.radians(center_lat))
    row_spacing_lat = row_spacing_m / METERS_PER_LAT_DEG

    rows = []
    lat = min_lat
    row_index = 0
    while lat <= max_lat:
        if row_index % 2 == 0:
            rows.append((lat, min_lon))
            rows.append((lat, max_lon))
        else:
            rows.append((lat, max_lon))
            rows.append((lat, min_lon))
        lat += row_spacing_lat
        row_index += 1

    kml_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    kml_lines.append('<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:wpml="http://www.dji.com/wpmz/1.0.6">')
    kml_lines.append('<Document>')
    kml_lines.append('<wpml:missionConfig>')
    kml_lines.append('  <wpml:flyToWaylineMode>safely</wpml:flyToWaylineMode>')
    kml_lines.append('  <wpml:finishAction>goHome</wpml:finishAction>')
    kml_lines.append('  <wpml:exitOnRCLost>goBack</wpml:exitOnRCLost>')
    kml_lines.append('</wpml:missionConfig>')
    kml_lines.append('<Folder>')
    kml_lines.append('<wpml:templateType>waypoint</wpml:templateType>')

    for i, (lat, lon) in enumerate(rows):
        kml_lines.append('<Placemark>')
        kml_lines.append(f'  <Point><coordinates>{lon},{lat},{altitude_m}</coordinates></Point>')
        kml_lines.append(f'  <wpml:index>{i}</wpml:index>')
        kml_lines.append(f'  <wpml:executeHeight>{altitude_m:.1f}</wpml:executeHeight>')
        kml_lines.append(f'  <wpml:waypointSpeed>{speed_ms}</wpml:waypointSpeed>')
        kml_lines.append('  <wpml:waypointHeadingParam>')
        kml_lines.append('    <wpml:waypointHeadingMode>smoothTransition</wpml:waypointHeadingMode>')
        kml_lines.append('  </wpml:waypointHeadingParam>')
        kml_lines.append('  <wpml:waypointTurnParam>')
        kml_lines.append('    <wpml:waypointTurnMode>toPointAndStopWithDiscontinuityCurvature</wpml:waypointTurnMode>')
        kml_lines.append('  </wpml:waypointTurnParam>')
        kml_lines.append('  <wpml:actionGroup>')
        kml_lines.append('    <wpml:action><wpml:actionActuatorFunc>startRecord</wpml:actionActuatorFunc></wpml:action>')
        kml_lines.append('  </wpml:actionGroup>')
        kml_lines.append('</Placemark>')

    kml_lines.append('</Folder>')
    kml_lines.append('</Document>')
    kml_lines.append('</kml>')
    kml_content = '\n'.join(kml_lines)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as kmz:
        kmz.writestr('waylines.wpml', kml_content)
    kmz_bytes = buf.getvalue()

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(kmz_bytes)
        print(f"Pass 1 grid saved to {out} ({len(rows)} waypoints, "
              f"row spacing {row_spacing_m:.1f}m, altitude {altitude_m:.0f}m)")

    return kmz_bytes


def run(detections_path: str, obstacles_path: str, output_path: str):
    with open(detections_path) as f:
        detection_data = json.load(f)

    clusters = detection_data['clusters']
    cowans = load_cowans(obstacles_path) if obstacles_path else []

    print(f"Generating Pass 2 waypoints for {len(clusters)} clusters...")
    kml_content = build_kml(clusters, cowans)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(str(out), 'w', zipfile.ZIP_DEFLATED) as kmz:
        kmz.writestr('waylines.wpml', kml_content)

    print(f"Pass 2 waypoints saved to {out}")
    print(f"Load into DJI Pilot 2 -> Route Mission -> Import KMZ")

    for i, cluster in enumerate(clusters):
        safe_alt = max(
            get_safe_altitude(cluster['lat'], cluster['lon'], cowans),
            MIN_INVESTIGATION_ALT_M
        )
        print(f"  WP{i+1}: {cluster['lat']:.5f},{cluster['lon']:.5f} "
              f"alt={safe_alt:.0f}m count={cluster['count']} conf={cluster['confidence']}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--detections', required=True)
    parser.add_argument('--obstacles', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    run(args.detections, args.obstacles, args.output)
