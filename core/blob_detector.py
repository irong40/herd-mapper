"""
Pass 1 processor: thermal images → deer cluster GPS coordinates

Input:  folder of thermal images from M4T Pass 1 grid mission
Output: list of cluster centroids with GPS coords, blob count, confidence score

Usage:
    python core/blob_detector.py --mission data/missions/MISSION_ID --output data/detections/
"""

import cv2
import numpy as np
import argparse
import json
import os
from pathlib import Path
from PIL import Image
import exifread
from scipy import ndimage


THERMAL_THRESHOLD = 200      # pixel intensity above background — tune per conditions
MIN_BLOB_AREA = 15           # pixels — filters noise, deer at altitude ~20-80px
CLUSTER_RADIUS_M = 30        # meters — blobs within this radius grouped as one herd
CONFIDENCE_MIN_AREA = 40     # blobs above this px area get HIGH confidence


def extract_gps(image_path: str) -> tuple[float, float] | None:
    with open(image_path, 'rb') as f:
        tags = exifread.process_file(f, stop_tag='GPS GPSLongitude')
    try:
        def dms_to_decimal(dms, ref):
            d, m, s = [float(x.num) / float(x.den) for x in dms.values]
            dd = d + m / 60 + s / 3600
            return -dd if ref.values[0] in ['S', 'W'] else dd

        lat = dms_to_decimal(tags['GPS GPSLatitude'], tags['GPS GPSLatitudeRef'])
        lon = dms_to_decimal(tags['GPS GPSLongitude'], tags['GPS GPSLongitudeRef'])
        return lat, lon
    except KeyError:
        return None


def detect_blobs(image_path: str) -> list[dict]:
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return []

    _, thresh = cv2.threshold(img, THERMAL_THRESHOLD, 255, cv2.THRESH_BINARY)
    labeled, num_features = ndimage.label(thresh)
    blobs = []

    for i in range(1, num_features + 1):
        component = labeled == i
        area = component.sum()
        if area < MIN_BLOB_AREA:
            continue

        cy, cx = ndimage.center_of_mass(component)
        confidence = 'HIGH' if area >= CONFIDENCE_MIN_AREA else 'MEDIUM'
        blobs.append({
            'pixel_x': float(cx),
            'pixel_y': float(cy),
            'area_px': int(area),
            'confidence': confidence,
        })

    return blobs


def pixel_to_gps(px, py, img_shape, center_gps, gsd_m_per_px=0.05):
    """Approximate GPS from pixel offset. GSD depends on altitude — tune for mission AGL."""
    h, w = img_shape
    dx = (px - w / 2) * gsd_m_per_px
    dy = (py - h / 2) * gsd_m_per_px
    lat = center_gps[0] + (dy / 111320)
    lon = center_gps[1] + (dx / (111320 * np.cos(np.radians(center_gps[0]))))
    return lat, lon


def cluster_detections(detections: list[dict], radius_m: float) -> list[dict]:
    """Group nearby detections into herds using simple distance clustering."""
    if not detections:
        return []

    clusters = []
    used = set()

    for i, d in enumerate(detections):
        if i in used:
            continue
        group = [d]
        used.add(i)
        for j, d2 in enumerate(detections):
            if j in used:
                continue
            dist = np.sqrt(
                ((d['lat'] - d2['lat']) * 111320) ** 2 +
                ((d['lon'] - d2['lon']) * 111320 * np.cos(np.radians(d['lat']))) ** 2
            )
            if dist <= radius_m:
                group.append(d2)
                used.add(j)

        centroid_lat = np.mean([x['lat'] for x in group])
        centroid_lon = np.mean([x['lon'] for x in group])
        max_conf = 'HIGH' if any(x['confidence'] == 'HIGH' for x in group) else 'MEDIUM'

        clusters.append({
            'lat': centroid_lat,
            'lon': centroid_lon,
            'count': len(group),
            'confidence': max_conf,
            'source_images': [x.get('source_image') for x in group],
        })

    return clusters


def run(mission_dir: str, output_dir: str):
    mission_path = Path(mission_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    all_detections = []
    thermal_images = list(mission_path.glob('*.jpg')) + list(mission_path.glob('*.JPG'))
    print(f"Processing {len(thermal_images)} thermal images...")

    for img_path in thermal_images:
        gps = extract_gps(str(img_path))
        if not gps:
            print(f"  No GPS in {img_path.name}, skipping")
            continue

        blobs = detect_blobs(str(img_path))
        img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)

        for blob in blobs:
            lat, lon = pixel_to_gps(
                blob['pixel_x'], blob['pixel_y'],
                img.shape, gps
            )
            blob['lat'] = lat
            blob['lon'] = lon
            blob['source_image'] = img_path.name
            all_detections.append(blob)

    clusters = cluster_detections(all_detections, CLUSTER_RADIUS_M)
    print(f"Found {len(all_detections)} blobs → {len(clusters)} clusters")

    mission_id = mission_path.name
    out_file = output_path / f"{mission_id}_detections.json"
    with open(out_file, 'w') as f:
        json.dump({
            'mission_id': mission_id,
            'total_blobs': len(all_detections),
            'clusters': clusters,
        }, f, indent=2)

    print(f"Saved detections to {out_file}")
    return clusters


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--mission', required=True, help='Path to mission folder with thermal images')
    parser.add_argument('--output', required=True, help='Output directory for detection JSON')
    args = parser.parse_args()
    run(args.mission, args.output)
