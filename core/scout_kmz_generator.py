"""
Scout KMZ generator — M4E Outer Guard property scout flight.

One-time-per-property scout that produces a persistent Cowan map at
`data/properties/{property_id}/cowans.json`. Subsequent census missions
load the cached Cowan map; no Outer Guard flight needed on census day.

Mission template: DJI mapping2d with `quickOrthoMappingEnable=1`
(M4E "Smart Oblique" — gimbal tilts at 3 angles per pass for thorough
oblique coverage of vertical structures: towers, power line poles,
fences, antennas). Pairs with `surfaceFollowModeEnable=1` for safe AGL
over rolling terrain.

Hazard inference happens AFTER the flight via `core/scout_processor.py`,
which runs visual_detector on captured oblique imagery and emits
Cowan-format dicts that merge into outer_guard.merge_visual_cowans
alongside the existing rangefinder path.

Usage (CLI):
    python -m core.scout_kmz_generator \\
        --property-kml data/properties/demo/bounds.kml \\
        --output data/properties/demo/scout.kmz

Verified WPML reference (developer.dji.com, 2026-05-08):
- M4E:  drone=99 sub=0  payload=88 (RGB only — no thermal lens)
- quickOrthoMappingEnable supported on M4E; pitch range [10, 30]°
- surfaceFollowModeEnable supported on M4E inside mapping templates
"""

import argparse
import io
import zipfile
from pathlib import Path

from sentinel_core.spatial import parse_kml

from core.waypoint_generator import (
    _mapping2d_template_kml,
    M4E_DRONE_SUB_ENUM,
    M4E_PAYLOAD_ENUM,
)


# Smart Oblique pitch — 20° = mid-range of [10, 30].  Lower = closer to nadir
# (better for ground), higher = more lateral (better for vertical structures).
# 20° is a good balance for fence/pole/tower edge capture.
DEFAULT_OBLIQUE_PITCH_DEG = 20

DEFAULT_SCOUT_ALTITUDE_M = 80.0   # higher than thermal grid (RGB has more reach)
DEFAULT_SCOUT_SPEED_MS = 6.0       # gentle to keep oblique frames sharp
DEFAULT_SCOUT_OVERLAP = 0.80        # higher than census — we want hazard surface coverage


def generate_scout_kmz(
    property_kml_path: str,
    altitude_m: float = DEFAULT_SCOUT_ALTITUDE_M,
    speed_ms: float = DEFAULT_SCOUT_SPEED_MS,
    overlap_pct: float = DEFAULT_SCOUT_OVERLAP,
    oblique_pitch_deg: int = DEFAULT_OBLIQUE_PITCH_DEG,
    output_path: str | None = None,
) -> bytes:
    """Emit M4E Outer Guard scout KMZ.

    Loads the property polygon, emits a mapping2d template with M4E payload,
    Smart Oblique enabled, and surface-follow.  Output is canonical
    `wpmz/template.kml` layout — drone Pilot 2 computes flight lines on import.
    """
    if not (10 <= oblique_pitch_deg <= 30):
        raise ValueError(
            f"oblique_pitch_deg must be in [10, 30] per WPML spec; got {oblique_pitch_deg}"
        )

    kml_data = parse_kml(property_kml_path)
    if not kml_data['polygons']:
        raise ValueError(f"No polygons found in {property_kml_path}")
    polygon = kml_data['polygons'][0]

    template_kml = _mapping2d_template_kml(
        polygon=polygon,
        altitude_m=altitude_m,
        speed_ms=speed_ms,
        overlap_pct=overlap_pct,
        drone_sub_enum=M4E_DRONE_SUB_ENUM,
        payload_enum=M4E_PAYLOAD_ENUM,
        payload_lens_index='wide',  # M4E has no thermal — RGB wide only
        quick_ortho_mapping_pitch=oblique_pitch_deg,
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as kmz:
        kmz.writestr('wpmz/template.kml', template_kml)
    kmz_bytes = buf.getvalue()

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(kmz_bytes)
        print(f"Outer Guard scout KMZ saved to {out}")
        print(f"  Polygon: {len(polygon)} vertices")
        print(f"  Surface-follow altitude: {altitude_m:.0f}m AGL")
        print(f"  Smart Oblique pitch: {oblique_pitch_deg}°")
        print(f"  Overlap: {int(overlap_pct * 100)}%")
        print(f"  Load into DJI Pilot 2 (M4E) -> Mapping Mission -> Import KMZ")

    return kmz_bytes


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--property-kml', required=True,
                        help='Property boundary KML (single polygon)')
    parser.add_argument('--output', required=True,
                        help='Output .kmz path')
    parser.add_argument('--altitude', type=float, default=DEFAULT_SCOUT_ALTITUDE_M,
                        help=f'Survey altitude AGL m (default {DEFAULT_SCOUT_ALTITUDE_M})')
    parser.add_argument('--speed', type=float, default=DEFAULT_SCOUT_SPEED_MS,
                        help=f'Flight speed m/s (default {DEFAULT_SCOUT_SPEED_MS})')
    parser.add_argument('--overlap', type=float, default=DEFAULT_SCOUT_OVERLAP,
                        help=f'Image overlap 0-1 (default {DEFAULT_SCOUT_OVERLAP})')
    parser.add_argument('--oblique-pitch', type=int, default=DEFAULT_OBLIQUE_PITCH_DEG,
                        help=f'Smart Oblique pitch degrees [10, 30] (default {DEFAULT_OBLIQUE_PITCH_DEG})')
    args = parser.parse_args()

    generate_scout_kmz(
        property_kml_path=args.property_kml,
        altitude_m=args.altitude,
        speed_ms=args.speed,
        overlap_pct=args.overlap,
        oblique_pitch_deg=args.oblique_pitch,
        output_path=args.output,
    )


if __name__ == '__main__':
    _cli()
