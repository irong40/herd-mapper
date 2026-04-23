"""
Waypoint generator: detection clusters + obstacle map → Pass 2 KMZ

For each detected cluster, calculates safe descent altitude and generates
a DJI Pilot 2 compatible KMZ waypoint file.

Usage:
    python core/waypoint_generator.py \
        --detections data/detections/MISSION_ID_detections.json \
        --obstacles data/obstacles/MISSION_ID_obstacles.json \
        --output data/missions/MISSION_ID/pass2.kmz
"""

import json
import argparse
import zipfile
import io
from pathlib import Path
from core.obstacle_mapper import get_safe_altitude, Obstacle


INVESTIGATION_SPEED_MS = 3.0    # m/s — slow for careful imaging
HOVER_SECONDS = 3               # pause at each target for dual capture
MIN_INVESTIGATION_ALT_M = 15    # never descend below this regardless of obstacles


def load_obstacles(path: str) -> list[Obstacle]:
    with open(path) as f:
        data = json.load(f)
    return [Obstacle(**o) for o in data]


def build_kml(clusters: list[dict], obstacles: list[Obstacle]) -> str:
    waypoints = []

    for i, cluster in enumerate(clusters):
        safe_alt = max(
            get_safe_altitude(cluster['lat'], cluster['lon'], obstacles),
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


def run(detections_path: str, obstacles_path: str, output_path: str):
    with open(detections_path) as f:
        detection_data = json.load(f)

    clusters = detection_data['clusters']
    obstacles = load_obstacles(obstacles_path) if obstacles_path else []

    print(f"Generating Pass 2 waypoints for {len(clusters)} clusters...")
    kml_content = build_kml(clusters, obstacles)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(str(out), 'w', zipfile.ZIP_DEFLATED) as kmz:
        kmz.writestr('waylines.wpml', kml_content)

    print(f"Pass 2 waypoints saved to {out}")
    print(f"Load into DJI Pilot 2 → Route Mission → Import KMZ")

    for i, cluster in enumerate(clusters):
        safe_alt = max(
            get_safe_altitude(cluster['lat'], cluster['lon'], obstacles),
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
