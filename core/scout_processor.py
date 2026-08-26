"""
Scout processor — ingests M4E Outer Guard scout imagery into a Cowan map.

Pipeline:
  M4E scout flight (KMZ from scout_kmz_generator)
    → Smart Oblique RGB images on SD card
    → Quick Transfer to laptop
    → THIS MODULE
    → data/properties/{property_id}/obstacles.json (persistent Cowan cache —
      the file api/server.py:load_property_obstacles reads)

Workflow:
  1. Run visual_detector.detect_from_folder on captured images.
  2. For each detection, enrich with capture-position GPS from EXIF.
     (Drone's GPS at capture time — proxy for hazard ground position.
      True ground projection via gimbal pitch/yaw + altitude is a Phase 2
      enhancement; 50m proximity merge with rangefinder Cowans tolerates this.)
  3. Strip internal-only fields (`_bbox`, `_image_path`).
  4. Persist to `data/properties/{property_id}/obstacles.json` with
     `last_scouted` ISO timestamp and an `obstacles` list — the exact
     path + format the API serves to the companion app.

Companion app reads the persistence file and surfaces a "scout
freshness" badge — if `last_scouted` is older than 6 months OR the
property bounds have changed, prompt operator to re-scout.

Subsequent census missions load this Cowan cache via outer_guard
without needing an Outer Guard flight on census day. Rangefinder
Cowans from real-time Pass 1 telemetry merge in alongside via
outer_guard.merge_visual_cowans (parallel path, not replacement).

Usage (CLI):
    python -m core.scout_processor \\
        --property-id demo \\
        --images data/properties/demo/scout_images/ \\
        --model models/obstacles.onnx
"""

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from core.visual_detector import detect_from_folder_with_provenance

try:
    from sentinel_core.metadata import extract_gps_from_exif
    _HAS_SENTINEL_METADATA = True
except ImportError:
    _HAS_SENTINEL_METADATA = False


logger = logging.getLogger(__name__)


SCOUT_FRESHNESS_DAYS = 180  # surface "refresh recommended" after 6 months


def _enrich_with_capture_gps(cowans: list[dict]) -> list[dict]:
    """For each Cowan, populate lat/lon from the capture image's EXIF GPS.

    Limitation: this places the Cowan at the drone's capture position, not
    the projected ground position of the detected object.  Adequate for
    merge with rangefinder Cowans (50m proximity match in
    outer_guard.merge_visual_cowans); a true oblique projection using
    gimbal pitch + altitude is a Phase 2 upgrade.
    """
    if not _HAS_SENTINEL_METADATA:
        logger.warning(
            "scout_processor: sentinel_core.metadata not available — "
            "Cowans will have lat/lon=None.  Install sentinel-core to enable."
        )
        return cowans

    enriched = []
    for cowan in cowans:
        image_path = cowan.get('_image_path')
        if image_path:
            gps = extract_gps_from_exif(image_path)
            if gps:
                lon, lat, _alt = gps
                cowan = {**cowan, 'lat': lat, 'lon': lon}
            else:
                logger.debug("No EXIF GPS for %s — Cowan lat/lon stays None", image_path)
        enriched.append(cowan)
    return enriched


def _strip_internal_fields(cowans: list[dict]) -> list[dict]:
    """Drop fields prefixed `_` before persisting (visual_detector convention)."""
    return [
        {k: v for k, v in c.items() if not k.startswith('_')}
        for c in cowans
    ]


def process_scout_imagery(
    property_id: str,
    image_dir: str,
    model_path: str | None = None,
    output_root: str = 'data/properties',
    conf_threshold: float = 0.45,
) -> dict:
    """Run scout image processing pipeline; persist Cowan cache.

    Returns
    -------
    dict
        {
          'property_id': str,
          'last_scouted': ISO 8601 UTC timestamp,
          'image_count': int,
          'cowan_count': int,
          'obstacles': list[dict],
          'output_path': str,
        }
    """
    image_path = Path(image_dir)
    if not image_path.is_dir():
        raise ValueError(f"Image directory not found: {image_dir}")

    print(f"Running visual detector on {image_dir}...")
    visual = detect_from_folder_with_provenance(
        str(image_path),
        model_path=model_path,
        conf_threshold=conf_threshold,
    )
    raw_cowans = visual['obstacles']
    print(f"  {len(raw_cowans)} raw Cowan detection(s) after dedup")

    enriched = _enrich_with_capture_gps(raw_cowans)
    persistable = _strip_internal_fields(enriched)

    # Count input images so the freshness UI can warn if the property bounds
    # changed after the last scout (sparse coverage = stale).
    image_files = [
        p for p in image_path.iterdir()
        if p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.tiff', '.tif'}
    ]

    record = {
        'property_id': property_id,
        'last_scouted': datetime.now(timezone.utc).isoformat(),
        'image_count': len(image_files),
        'cowan_count': len(persistable),
        # Provenance travels with the cache: a scout run with no model must be
        # distinguishable from a scout run that genuinely found nothing.
        'visual_mode': visual['mode'],
        'visual_model_path': visual['model_path'],
        'visual_degraded': visual['mode'] != 'onnx',
        'obstacles': persistable,
    }

    out_dir = Path(output_root) / property_id
    out_dir.mkdir(parents=True, exist_ok=True)
    # obstacles.json is THE file api/server.py reads (load_property_obstacles)
    # — previously this wrote cowans.json, which nothing served, so real
    # scout output never reached the companion app.
    out_file = out_dir / 'obstacles.json'
    tmp = out_file.with_suffix('.tmp')
    with open(tmp, 'w') as f:
        json.dump(record, f, indent=2, default=str)
    tmp.replace(out_file)

    record['output_path'] = str(out_file)
    print(f"Cowan cache saved to {out_file}")
    print(f"  Scouted images: {record['image_count']}")
    print(f"  Cowans cached: {record['cowan_count']}")
    print(f"  Last scouted: {record['last_scouted']}")
    return record


def load_cached_cowans(property_id: str, root: str = 'data/properties') -> dict | None:
    """Load persisted Cowan cache for a property.

    Reads obstacles.json (canonical, shared with the API); falls back to
    the legacy cowans.json written before 2026-07-04.  Returns the full
    record (with `last_scouted`, etc.) normalised to carry an `obstacles`
    key, or None if absent.  Census missions call this on startup; if None
    or stale, the companion app prompts the operator to run an Outer Guard
    scout flight.
    """
    prop_dir = Path(root) / property_id
    for filename in ('obstacles.json', 'cowans.json'):
        cache_file = prop_dir / filename
        if not cache_file.is_file():
            continue
        with open(cache_file) as f:
            record = json.load(f)
        if isinstance(record, list):
            # Bare list (mock_data format) — wrap for a uniform return shape
            record = {'property_id': property_id, 'obstacles': record}
        elif 'obstacles' not in record and 'cowans' in record:
            record['obstacles'] = record.pop('cowans')  # legacy key
        return record
    return None


def is_scout_stale(record: dict, max_age_days: int = SCOUT_FRESHNESS_DAYS) -> bool:
    """Return True if the cached scout is older than max_age_days."""
    if not record or 'last_scouted' not in record:
        return True
    try:
        last = datetime.fromisoformat(record['last_scouted'].replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return True
    age = datetime.now(timezone.utc) - last
    return age.days > max_age_days


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--property-id', required=True,
                        help='Property identifier (e.g. demo)')
    parser.add_argument('--images', required=True,
                        help='Directory of M4E scout images')
    parser.add_argument('--model', default=None,
                        help='Path to obstacles.onnx (omit = mock mode)')
    parser.add_argument('--output-root', default='data/properties',
                        help='Root directory for property data (default: data/properties)')
    parser.add_argument('--conf', type=float, default=0.45,
                        help='Detection confidence threshold (default 0.45)')
    args = parser.parse_args()

    process_scout_imagery(
        property_id=args.property_id,
        image_dir=args.images,
        model_path=args.model,
        output_root=args.output_root,
        conf_threshold=args.conf,
    )


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s  %(message)s')
    _cli()
