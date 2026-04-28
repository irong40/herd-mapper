"""
Demo mock data generator — simulates Pass 1 results for a 50-acre property.

Usage:
    python core/mock_data.py --mode scout    # airspace tiling only (M4E pre-mission)
    python core/mock_data.py --mode census   # full census (detections + property hazards)
    python core/mock_data.py                 # defaults to census
"""

import argparse
import json
import math
import csv
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


def generate_bounds():
    north_lat, _ = offset(CENTER_LAT, CENTER_LON, 0,  HALF_M)
    south_lat, _ = offset(CENTER_LAT, CENTER_LON, 0, -HALF_M)
    _, east_lon  = offset(CENTER_LAT, CENTER_LON,  HALF_M, 0)
    _, west_lon  = offset(CENTER_LAT, CENTER_LON, -HALF_M, 0)
    return {
        'north': north_lat, 'south': south_lat,
        'east':  east_lon,  'west':  west_lon,
        'center_lat': CENTER_LAT, 'center_lon': CENTER_LON,
        'name': 'Demo Property — 50 acres',
    }


def generate_cowans():
    cowans = []

    # Fence — north boundary (post pattern)
    fence_north_y = HALF_M - 20
    for dx in range(-200, 210, 12):
        lat, lon = offset(CENTER_LAT, CENTER_LON, dx, fence_north_y)
        cowans.append({
            'id': f'fence_n_{dx}',
            'lat': lat, 'lon': lon,
            'height_m': 6.0,
            'type': 'fence_line',
            'confidence': 'MEDIUM',
            'exclusion_radius_m': 4.0,
            'note': 'Post pattern inferred — north boundary',
        })

    # Power line — diagonal NW to SE
    for i, t in enumerate([x / 10 for x in range(0, 11)]):
        dx = -180 + t * 360
        dy =  160 - t * 320
        lat, lon = offset(CENTER_LAT, CENTER_LON, dx, dy)
        cowans.append({
            'id': f'power_{i}',
            'lat': lat, 'lon': lon,
            'height_m': 14.0,
            'type': 'power_line',
            'confidence': 'HIGH',
            'exclusion_radius_m': 8.0,
            'note': 'OSM confirmed — utility corridor',
        })

    # Tower — near field center cluster, LOW confidence (requires operator resolution)
    # Placed 28m from cluster_003 so its exclusion zone locks that waypoint
    tower_lat, tower_lon = offset(CENTER_LAT, CENTER_LON, 100, 20)
    cowans.append({
        'id': 'tower_0',
        'lat': tower_lat, 'lon': tower_lon,
        'height_m': 22.0,
        'type': 'tower',
        'confidence': 'LOW',
        'exclusion_radius_m': 33.0,
        'note': 'Guy wire exclusion cone 33m radius',
    })

    return cowans


def generate_flight_log(output_path: str, altitude_agl_m: float = 60.0):
    """Generate a mock DJI-style CSV flight log with rangefinder data."""
    fieldnames = ['latitude', 'longitude', 'altitude', 'ultrasonic_height']
    
    # Simulate a simple lawnmower pattern
    readings = []
    
    # Add some hazards to the telemetry
    # Power line at -180, 160 to 180, -160
    
    for row in range(-200, 201, 20):
        for col in range(-200, 201, 5):
            lat, lon = offset(CENTER_LAT, CENTER_LON, col, row)
            
            # Default: ground is far away (rangefinder = altitude)
            range_m = altitude_agl_m
            
            # Check if we are over a mock power line pole
            # (Simplified: if near one of our generated cowan points)
            for c in generate_cowans():
                dist = math.sqrt((col - (c['lon']-CENTER_LON)/DEG_PER_M_LON)**2 + 
                                 (row - (c['lat']-CENTER_LAT)/DEG_PER_M_LAT)**2)
                if dist < 5.0:
                    range_m = altitude_agl_m - c['height_m']
                    break
            
            readings.append({
                'latitude': lat,
                'longitude': lon,
                'altitude': altitude_agl_m,
                'ultrasonic_height': range_m
            })

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(readings)


def generate_lake():
    lake_lat, lake_lon = offset(CENTER_LAT, CENTER_LON, -60, -80)
    return {
        'center_lat': lake_lat,
        'center_lon': lake_lon,
        'radius_m': 45,
        'label': 'Pond',
    }


def generate_detections():
    clusters = []
    # Cluster 1 — herd near pond edge, HIGH confidence
    lat1, lon1 = offset(CENTER_LAT, CENTER_LON, -40, -60)
    clusters.append({
        'id': 'cluster_001',
        'lat': lat1, 'lon': lon1,
        'count': 8,
        'confidence': 'HIGH',
        'label': 'Herd near pond edge',
        'source_images': ['DJI_20260423_054312_0041_T.JPG', 'DJI_20260423_054318_0042_T.JPG'],
    })
    # Cluster 2 — bedded group NW of pond, HIGH confidence
    lat2, lon2 = offset(CENTER_LAT, CENTER_LON, -110, -30)
    clusters.append({
        'id': 'cluster_002',
        'lat': lat2, 'lon': lon2,
        'count': 7,
        'confidence': 'HIGH',
        'label': 'Bedded group — pond NW',
        'source_images': ['DJI_20260423_054401_0048_T.JPG'],
    })
    # Cluster 3 — field center, MEDIUM confidence
    lat3, lon3 = offset(CENTER_LAT, CENTER_LON, 80, 40)
    clusters.append({
        'id': 'cluster_003',
        'lat': lat3, 'lon': lon3,
        'count': 3,
        'confidence': 'MEDIUM',
        'label': 'Possible deer — field center',
        'source_images': ['DJI_20260423_054512_0057_T.JPG'],
    })
    # Cluster 4 — treeline, MEDIUM confidence
    lat4, lon4 = offset(CENTER_LAT, CENTER_LON, -170, 60)
    clusters.append({
        'id': 'cluster_004',
        'lat': lat4, 'lon': lon4,
        'count': 4,
        'confidence': 'MEDIUM',
        'label': 'Treeline movement',
        'source_images': ['DJI_20260423_054601_0063_T.JPG'],
    })
    return {
        'mission_id': 'demo',
        'property_id': 'demo',
        'pass1_agl_ft': 200,
        'total_blobs': 22,
        'clusters': clusters,
    }


def run_scout(property_id='demo'):
    prop_dir = Path(f'data/properties/{property_id}')
    prop_dir.mkdir(parents=True, exist_ok=True)

    bounds = generate_bounds()
    cowans = generate_cowans()
    lake   = generate_lake()

    with open(prop_dir / 'bounds.json', 'w') as f:
        json.dump(bounds, f, indent=2)
    with open(prop_dir / 'obstacles.json', 'w') as f:
        json.dump(cowans, f, indent=2)
    with open(prop_dir / 'lake.json', 'w') as f:
        json.dump(lake, f, indent=2)

    mission_id  = f'{property_id}_scout'
    mission_dir = Path(f'data/missions/{mission_id}')
    mission_dir.mkdir(parents=True, exist_ok=True)

    with open(mission_dir / 'config.json', 'w') as f:
        json.dump({'mission_id': mission_id, 'property_id': property_id, 'mission_type': 'scout', 'drone': 'M4E'}, f, indent=2)

    log_file = mission_dir / 'flight_log.csv'
    generate_flight_log(str(log_file))

    print(f"Scout data generated for property '{property_id}':")
    print(f"  {len(cowans)} obstacles -> data/properties/{property_id}/obstacles.json")
    print(f"  Mock flight log -> {log_file}")


def run_census(property_id='demo', mission_id='demo'):
    # Write the shared property layer (bounds, obstacles, lake)
    run_scout(property_id=property_id)

    # Write mission-specific data
    mission_dir = Path(f'data/missions/{mission_id}')
    mission_dir.mkdir(parents=True, exist_ok=True)

    with open(mission_dir / 'config.json', 'w') as f:
        json.dump({'mission_id': mission_id, 'property_id': property_id, 'mission_type': 'census', 'drone': 'M4T'}, f, indent=2)

    detections = generate_detections()
    with open(mission_dir / 'detections.json', 'w') as f:
        json.dump(detections, f, indent=2)

    print(f"Census data generated for mission '{mission_id}' (property '{property_id}'):")
    print(f"  {len(detections['clusters'])} clusters ({detections['total_blobs']} blobs) -> data/missions/{mission_id}/detections.json")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['scout', 'census'], default='census')
    parser.add_argument('--property', default='demo')
    parser.add_argument('--mission', default='demo')
    args = parser.parse_args()

    if args.mode == 'scout':
        run_scout(property_id=args.property)
    else:
        run_census(property_id=args.property, mission_id=args.mission)
