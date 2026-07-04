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
import sys
import zipfile
import io
from pathlib import Path

# Allow the documented `python core/waypoint_generator.py ...` invocation
# (same shim as pipeline_runner) in addition to `python -m core.waypoint_generator`.
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.outer_guard import get_safe_altitude, get_waypoint_lock, Cowan
from sentinel_core.spatial import parse_kml, kml_bbox, METERS_PER_LAT_DEG


INVESTIGATION_SPEED_MS = 3.0    # m/s — slow for careful imaging
HOVER_SECONDS = 3               # pause at each target for dual capture
MIN_INVESTIGATION_ALT_M = 15    # never descend below this regardless of obstacles
RTH_BUFFER_M = 30               # added above tallest known Cowan for global RTH height
TAKEOFF_SECURITY_HEIGHT_M = 20  # auto-climb to this before route start (RC-launch min 1.2)
TRANSITIONAL_SPEED_MS = 5.0     # speed between waypoints when not in waypointSpeed scope

# M4T thermal sensor (640×512, ~45° HFOV) swath width at given altitude
_M4T_HFOV_DEG = 45.0

# DJI Pilot 2 / WPML enums (verified against developer.dji.com WPML reference)
# M4T = drone 99, sub 1, payload 89.  M4E = drone 99, sub 0, payload 88.
M4T_DRONE_ENUM = 99
M4T_DRONE_SUB_ENUM = 1
M4T_PAYLOAD_ENUM = 89
M4E_DRONE_SUB_ENUM = 0
M4E_PAYLOAD_ENUM = 88


def load_cowans(path: str) -> list[Cowan]:
    """Load Cowans from a tiled-airspace or obstacles JSON file.

    Accepts either a bare list (legacy / mock_data format) or a dict
    wrapper with a 'cowans' or 'obstacles' key (tile_airspace now writes
    {'rangefinder_missing': ..., 'cowans': [...]}).
    """
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        if data.get('rangefinder_missing'):
            print(
                "  *** WARNING: obstacle file is DEGRADED — flight log had no "
                "rangefinder column; rangefinder hazards are absent. ***"
            )
        data = data.get('cowans', data.get('obstacles', []))
    return [Cowan(**o) for o in data]


def load_resolutions(
    resolutions_path: str | None = None,
    mission_id: str | None = None,
    property_id: str | None = None,
    data_dir: str | Path = 'data',
) -> dict:
    """Load operator hazard resolutions with the same precedence as
    api/server.py: explicit path > property-level > legacy mission-level.

    Returns {} when nothing is found — which is the CONSERVATIVE case:
    with no resolutions, every LOW-confidence obstacle is treated as
    unresolved and clusters inside its exclusion zone are EXCLUDED from
    the KMZ (matching the companion app's locked-waypoint rule).
    """
    data_dir = Path(data_dir)
    candidates = []
    if resolutions_path:
        candidates.append(Path(resolutions_path))
    if property_id:
        candidates.append(data_dir / 'properties' / property_id / 'resolutions.json')
    if mission_id:
        candidates.append(data_dir / 'resolutions' / f'{mission_id}.json')
    for path in candidates:
        if path.is_file():
            with open(path) as f:
                return json.load(f)
    return {}


def _global_rth_height(waypoints: list[dict], cowans: list[Cowan]) -> float:
    """Tallest of: max waypoint exec alt, max known Cowan height + RTH buffer."""
    max_wp = max((wp['alt_m'] for wp in waypoints), default=MIN_INVESTIGATION_ALT_M)
    max_cowan = max((c.height_m for c in cowans), default=0.0)
    return max(max_wp, max_cowan + RTH_BUFFER_M)


def plan_waypoints(
    clusters: list[dict],
    cowans: list[Cowan],
    resolutions: dict | None = None,
) -> tuple[list[dict], list[dict]]:
    """Compute flyable Pass 2 waypoints, enforcing the SAME safety gates as
    the companion app (api/server.py):

    - Altitude: core.outer_guard.get_safe_altitude — the single shared
      function, so the KMZ executeHeight is identical to the UI value.
    - Locking:  core.outer_guard.get_waypoint_lock — clusters locked by an
      unresolved or hazard-confirmed LOW-confidence obstacle are EXCLUDED
      from the KMZ entirely.  The flown artifact must never visit a
      waypoint the UI shows as locked.

    Returns (flyable_waypoints, excluded) where excluded entries carry
    'locked_by' / 'lock_reason' for operator display.
    """
    resolutions = resolutions or {}
    waypoints = []
    excluded = []
    for cluster in clusters:
        locked_by, lock_reason = get_waypoint_lock(
            cluster['lat'], cluster['lon'], cowans, resolutions
        )
        if locked_by is not None:
            excluded.append({
                'lat': cluster['lat'],
                'lon': cluster['lon'],
                'count': cluster.get('count'),
                'id': cluster.get('id', ''),
                'locked_by': locked_by,
                'lock_reason': lock_reason,
            })
            continue
        safe_alt = max(
            get_safe_altitude(cluster['lat'], cluster['lon'], cowans),
            MIN_INVESTIGATION_ALT_M,
        )
        waypoints.append({
            'index': len(waypoints),
            'lat': cluster['lat'],
            'lon': cluster['lon'],
            'alt_m': safe_alt,
            'count': cluster['count'],
            'confidence': cluster['confidence'],
        })
    return waypoints, excluded


def build_kml(
    clusters: list[dict],
    cowans: list[Cowan],
    resolutions: dict | None = None,
) -> str:
    """Emit Pass 2 cluster-visit KMZ (waylines.wpml content) for M4T.

    SAFETY: clusters locked under the companion-app rules (unresolved or
    hazard-confirmed LOW-confidence obstacles — see plan_waypoints) are
    excluded from the emitted route.  Passing resolutions=None means "no
    operator resolutions", which locks every cluster near a LOW-confidence
    obstacle (conservative default).

    Verified against developer.dji.com WPML reference (cloud-api-tutorial,
    common-element + waylines-wpml, 2026-05-08):
      - actionGroup requires id, start/end index, mode, actionTrigger
      - payloadLensIndex is comma-string (`wide,ir`), not an int
      - startActionGroup at Folder level fires once before route begins
      - droneEnumValue=99 + droneSubEnumValue=1 disambiguates M4T from M4E
    """
    waypoints, excluded = plan_waypoints(clusters, cowans, resolutions)
    for ex in excluded:
        print(
            f"  SAFETY: cluster {ex['id'] or '?'} at "
            f"{ex['lat']:.5f},{ex['lon']:.5f} EXCLUDED from KMZ — "
            f"{ex['lock_reason']}. Resolve it in the companion app to include."
        )

    rth_height = _global_rth_height(waypoints, cowans)

    kml = ['<?xml version="1.0" encoding="UTF-8"?>']
    kml.append('<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:wpml="http://www.dji.com/wpmz/1.0.6">')
    kml.append('<Document>')
    kml.append('<wpml:missionConfig>')
    kml.append('  <wpml:flyToWaylineMode>safely</wpml:flyToWaylineMode>')
    kml.append('  <wpml:finishAction>goHome</wpml:finishAction>')
    kml.append('  <wpml:exitOnRCLost>executeLostAction</wpml:exitOnRCLost>')
    kml.append('  <wpml:executeRCLostAction>goBack</wpml:executeRCLostAction>')
    kml.append(f'  <wpml:takeOffSecurityHeight>{TAKEOFF_SECURITY_HEIGHT_M}</wpml:takeOffSecurityHeight>')
    kml.append(f'  <wpml:globalTransitionalSpeed>{TRANSITIONAL_SPEED_MS}</wpml:globalTransitionalSpeed>')
    kml.append(f'  <wpml:globalRTHHeight>{rth_height:.1f}</wpml:globalRTHHeight>')
    kml.append(f'  <wpml:droneInfo>')
    kml.append(f'    <wpml:droneEnumValue>{M4T_DRONE_ENUM}</wpml:droneEnumValue>')
    kml.append(f'    <wpml:droneSubEnumValue>{M4T_DRONE_SUB_ENUM}</wpml:droneSubEnumValue>')
    kml.append(f'  </wpml:droneInfo>')
    kml.append(f'  <wpml:payloadInfo>')
    kml.append(f'    <wpml:payloadEnumValue>{M4T_PAYLOAD_ENUM}</wpml:payloadEnumValue>')
    kml.append(f'    <wpml:payloadPositionIndex>0</wpml:payloadPositionIndex>')
    kml.append(f'  </wpml:payloadInfo>')
    kml.append('</wpml:missionConfig>')

    kml.append('<Folder>')
    kml.append('  <wpml:templateId>0</wpml:templateId>')
    kml.append('  <wpml:waylineId>0</wpml:waylineId>')
    kml.append('  <wpml:templateType>waypoint</wpml:templateType>')
    kml.append('  <wpml:executeHeightMode>relativeToStartPoint</wpml:executeHeightMode>')
    kml.append(f'  <wpml:autoFlightSpeed>{INVESTIGATION_SPEED_MS}</wpml:autoFlightSpeed>')

    # Mission-start: lock gimbal to nadir before first waypoint.
    kml.append('  <wpml:startActionGroup>')
    kml.append('    <wpml:actionGroupId>0</wpml:actionGroupId>')
    kml.append('    <wpml:actionGroupStartIndex>0</wpml:actionGroupStartIndex>')
    kml.append('    <wpml:actionGroupEndIndex>0</wpml:actionGroupEndIndex>')
    kml.append('    <wpml:actionGroupMode>sequence</wpml:actionGroupMode>')
    kml.append('    <wpml:actionTrigger>')
    kml.append('      <wpml:actionTriggerType>reachPoint</wpml:actionTriggerType>')
    kml.append('    </wpml:actionTrigger>')
    kml.append('    <wpml:action>')
    kml.append('      <wpml:actionId>0</wpml:actionId>')
    kml.append('      <wpml:actionActuatorFunc>gimbalRotate</wpml:actionActuatorFunc>')
    kml.append('      <wpml:actionActuatorFuncParam>')
    kml.append('        <wpml:gimbalHeadingYawBase>north</wpml:gimbalHeadingYawBase>')
    kml.append('        <wpml:gimbalRotateMode>absoluteAngle</wpml:gimbalRotateMode>')
    kml.append('        <wpml:gimbalPitchRotateEnable>1</wpml:gimbalPitchRotateEnable>')
    kml.append('        <wpml:gimbalPitchRotateAngle>-90</wpml:gimbalPitchRotateAngle>')
    kml.append('        <wpml:gimbalRollRotateEnable>0</wpml:gimbalRollRotateEnable>')
    kml.append('        <wpml:gimbalRollRotateAngle>0</wpml:gimbalRollRotateAngle>')
    kml.append('        <wpml:gimbalYawRotateEnable>0</wpml:gimbalYawRotateEnable>')
    kml.append('        <wpml:gimbalYawRotateAngle>0</wpml:gimbalYawRotateAngle>')
    kml.append('        <wpml:gimbalRotateTimeEnable>0</wpml:gimbalRotateTimeEnable>')
    kml.append('        <wpml:gimbalRotateTime>0</wpml:gimbalRotateTime>')
    kml.append('        <wpml:payloadPositionIndex>0</wpml:payloadPositionIndex>')
    kml.append('      </wpml:actionActuatorFuncParam>')
    kml.append('    </wpml:action>')
    kml.append('  </wpml:startActionGroup>')

    for wp in waypoints:
        kml.append('<Placemark>')
        kml.append(f'  <Point><coordinates>{wp["lon"]},{wp["lat"]},{wp["alt_m"]}</coordinates></Point>')
        kml.append(f'  <wpml:index>{wp["index"]}</wpml:index>')
        kml.append(f'  <wpml:executeHeight>{wp["alt_m"]:.1f}</wpml:executeHeight>')
        kml.append(f'  <wpml:waypointSpeed>{INVESTIGATION_SPEED_MS}</wpml:waypointSpeed>')
        kml.append('  <wpml:waypointHeadingParam>')
        kml.append('    <wpml:waypointHeadingMode>smoothTransition</wpml:waypointHeadingMode>')
        kml.append('  </wpml:waypointHeadingParam>')
        kml.append('  <wpml:waypointTurnParam>')
        kml.append('    <wpml:waypointTurnMode>toPointAndStopWithDiscontinuityCurvature</wpml:waypointTurnMode>')
        kml.append('  </wpml:waypointTurnParam>')

        # Per-waypoint actionGroup: hover, then dual-lens (wide+thermal) photo.
        # Single takePhoto with payloadLensIndex=wide,ir captures both files at once.
        kml.append('  <wpml:actionGroup>')
        kml.append(f'    <wpml:actionGroupId>{wp["index"] + 1}</wpml:actionGroupId>')
        kml.append(f'    <wpml:actionGroupStartIndex>{wp["index"]}</wpml:actionGroupStartIndex>')
        kml.append(f'    <wpml:actionGroupEndIndex>{wp["index"]}</wpml:actionGroupEndIndex>')
        kml.append('    <wpml:actionGroupMode>sequence</wpml:actionGroupMode>')
        kml.append('    <wpml:actionTrigger>')
        kml.append('      <wpml:actionTriggerType>reachPoint</wpml:actionTriggerType>')
        kml.append('    </wpml:actionTrigger>')
        kml.append('    <wpml:action>')
        kml.append('      <wpml:actionId>0</wpml:actionId>')
        kml.append('      <wpml:actionActuatorFunc>hover</wpml:actionActuatorFunc>')
        kml.append('      <wpml:actionActuatorFuncParam>')
        kml.append(f'        <wpml:hoverTime>{HOVER_SECONDS}</wpml:hoverTime>')
        kml.append('      </wpml:actionActuatorFuncParam>')
        kml.append('    </wpml:action>')
        kml.append('    <wpml:action>')
        kml.append('      <wpml:actionId>1</wpml:actionId>')
        kml.append('      <wpml:actionActuatorFunc>takePhoto</wpml:actionActuatorFunc>')
        kml.append('      <wpml:actionActuatorFuncParam>')
        kml.append('        <wpml:payloadPositionIndex>0</wpml:payloadPositionIndex>')
        kml.append(f'        <wpml:fileSuffix>cluster_{wp["index"]}</wpml:fileSuffix>')
        kml.append('        <wpml:useGlobalPayloadLensIndex>0</wpml:useGlobalPayloadLensIndex>')
        kml.append('        <wpml:payloadLensIndex>wide,ir</wpml:payloadLensIndex>')
        kml.append('      </wpml:actionActuatorFuncParam>')
        kml.append('    </wpml:action>')
        kml.append('  </wpml:actionGroup>')

        kml.append(f'  <!-- cluster_count:{wp["count"]} confidence:{wp["confidence"]} -->')
        kml.append('</Placemark>')

    kml.append('</Folder>')
    kml.append('</Document>')
    kml.append('</kml>')
    return '\n'.join(kml)


def _mapping2d_template_kml(
    polygon: list[tuple[float, float]],
    altitude_m: float,
    speed_ms: float,
    overlap_pct: float,
    drone_sub_enum: int,
    payload_enum: int,
    payload_lens_index: str,
    quick_ortho_mapping_pitch: int | None = None,
) -> str:
    """Emit a DJI WPML 1.0.x mapping2d template KML for terrain-following Pass 1.

    Verified against developer.dji.com WPML reference (template-kml.html).
    Drone computes the lawnmower grid from polygon + height + overlap.
    M4T `surfaceFollowModeEnable=1` provides terrain-follow at constant AGL.
    """
    overlap_int = int(round(overlap_pct * 100))
    coords_str = ' '.join(f'{lon:.7f},{lat:.7f},0' for lat, lon in polygon)

    kml = ['<?xml version="1.0" encoding="UTF-8"?>']
    kml.append('<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:wpml="http://www.dji.com/wpmz/1.0.6">')
    kml.append('<Document>')
    kml.append('<wpml:missionConfig>')
    kml.append('  <wpml:flyToWaylineMode>safely</wpml:flyToWaylineMode>')
    kml.append('  <wpml:finishAction>goHome</wpml:finishAction>')
    kml.append('  <wpml:exitOnRCLost>executeLostAction</wpml:exitOnRCLost>')
    kml.append('  <wpml:executeRCLostAction>goBack</wpml:executeRCLostAction>')
    kml.append(f'  <wpml:takeOffSecurityHeight>{TAKEOFF_SECURITY_HEIGHT_M}</wpml:takeOffSecurityHeight>')
    kml.append(f'  <wpml:globalTransitionalSpeed>{TRANSITIONAL_SPEED_MS}</wpml:globalTransitionalSpeed>')
    # RTH must clear survey altitude with margin; survey-area Cowans aren't
    # known yet during pre-flight, so use altitude + RTH buffer.
    kml.append(f'  <wpml:globalRTHHeight>{altitude_m + RTH_BUFFER_M:.1f}</wpml:globalRTHHeight>')
    kml.append('  <wpml:droneInfo>')
    kml.append(f'    <wpml:droneEnumValue>{M4T_DRONE_ENUM}</wpml:droneEnumValue>')
    kml.append(f'    <wpml:droneSubEnumValue>{drone_sub_enum}</wpml:droneSubEnumValue>')
    kml.append('  </wpml:droneInfo>')
    kml.append('  <wpml:payloadInfo>')
    kml.append(f'    <wpml:payloadEnumValue>{payload_enum}</wpml:payloadEnumValue>')
    kml.append('    <wpml:payloadPositionIndex>0</wpml:payloadPositionIndex>')
    kml.append('  </wpml:payloadInfo>')
    kml.append('</wpml:missionConfig>')

    kml.append('<Folder>')
    kml.append('  <wpml:templateId>0</wpml:templateId>')
    kml.append('  <wpml:templateType>mapping2d</wpml:templateType>')
    kml.append('  <wpml:waylineCoordinateSysParam>')
    kml.append('    <wpml:coordinateMode>WGS84</wpml:coordinateMode>')
    kml.append('    <wpml:heightMode>relativeToStartPoint</wpml:heightMode>')
    kml.append('    <wpml:positioningType>GPS</wpml:positioningType>')
    # surfaceFollowModeEnable: drone uses onboard DEM to maintain constant AGL
    # over rolling terrain.  Supported on M4E/M4T per template-kml.html.
    kml.append('    <wpml:surfaceFollowModeEnable>1</wpml:surfaceFollowModeEnable>')
    kml.append(f'    <wpml:surfaceRelativeHeight>{altitude_m:.1f}</wpml:surfaceRelativeHeight>')
    kml.append('  </wpml:waylineCoordinateSysParam>')
    kml.append(f'  <wpml:autoFlightSpeed>{speed_ms}</wpml:autoFlightSpeed>')
    kml.append('  <wpml:caliFlightEnable>0</wpml:caliFlightEnable>')
    kml.append('  <wpml:gimbalPitchMode>manual</wpml:gimbalPitchMode>')
    kml.append('  <wpml:globalUseStraightLine>1</wpml:globalUseStraightLine>')

    # Mission-start: lock gimbal to nadir before survey begins.
    kml.append('  <wpml:startActionGroup>')
    kml.append('    <wpml:actionGroupId>0</wpml:actionGroupId>')
    kml.append('    <wpml:actionGroupStartIndex>0</wpml:actionGroupStartIndex>')
    kml.append('    <wpml:actionGroupEndIndex>0</wpml:actionGroupEndIndex>')
    kml.append('    <wpml:actionGroupMode>sequence</wpml:actionGroupMode>')
    kml.append('    <wpml:actionTrigger>')
    kml.append('      <wpml:actionTriggerType>reachPoint</wpml:actionTriggerType>')
    kml.append('    </wpml:actionTrigger>')
    kml.append('    <wpml:action>')
    kml.append('      <wpml:actionId>0</wpml:actionId>')
    kml.append('      <wpml:actionActuatorFunc>gimbalRotate</wpml:actionActuatorFunc>')
    kml.append('      <wpml:actionActuatorFuncParam>')
    kml.append('        <wpml:gimbalHeadingYawBase>north</wpml:gimbalHeadingYawBase>')
    kml.append('        <wpml:gimbalRotateMode>absoluteAngle</wpml:gimbalRotateMode>')
    kml.append('        <wpml:gimbalPitchRotateEnable>1</wpml:gimbalPitchRotateEnable>')
    kml.append('        <wpml:gimbalPitchRotateAngle>-90</wpml:gimbalPitchRotateAngle>')
    kml.append('        <wpml:gimbalRollRotateEnable>0</wpml:gimbalRollRotateEnable>')
    kml.append('        <wpml:gimbalRollRotateAngle>0</wpml:gimbalRollRotateAngle>')
    kml.append('        <wpml:gimbalYawRotateEnable>0</wpml:gimbalYawRotateEnable>')
    kml.append('        <wpml:gimbalYawRotateAngle>0</wpml:gimbalYawRotateAngle>')
    kml.append('        <wpml:gimbalRotateTimeEnable>0</wpml:gimbalRotateTimeEnable>')
    kml.append('        <wpml:gimbalRotateTime>0</wpml:gimbalRotateTime>')
    kml.append('        <wpml:payloadPositionIndex>0</wpml:payloadPositionIndex>')
    kml.append('      </wpml:actionActuatorFuncParam>')
    kml.append('    </wpml:action>')
    kml.append('  </wpml:startActionGroup>')

    # Survey polygon — drone computes lawnmower from this.
    kml.append('  <Placemark>')
    kml.append('    <Polygon>')
    kml.append('      <outerBoundaryIs>')
    kml.append('        <LinearRing>')
    kml.append(f'          <coordinates>{coords_str}</coordinates>')
    kml.append('        </LinearRing>')
    kml.append('      </outerBoundaryIs>')
    kml.append('    </Polygon>')
    kml.append('  </Placemark>')

    # Mapping settings.  smartObliqueEnable (legacy P1 oblique pose) is M4E-only
    # for `quickOrthoMappingEnable`; we emit smartObliqueEnable=0 to be explicit.
    kml.append(f'  <wpml:height>{altitude_m:.1f}</wpml:height>')
    kml.append(f'  <wpml:ellipsoidHeight>{altitude_m:.1f}</wpml:ellipsoidHeight>')
    kml.append('  <wpml:overlap>')
    kml.append(f'    <wpml:orthoCameraOverlapH>{overlap_int}</wpml:orthoCameraOverlapH>')
    kml.append(f'    <wpml:orthoCameraOverlapW>{overlap_int}</wpml:orthoCameraOverlapW>')
    kml.append('  </wpml:overlap>')
    kml.append('  <wpml:elevationOptimizeEnable>0</wpml:elevationOptimizeEnable>')
    # smartObliqueEnable: legacy P1-on-M300 oblique pose; never used here.
    kml.append('  <wpml:smartObliqueEnable>0</wpml:smartObliqueEnable>')
    # quickOrthoMappingEnable: M4E "Smart Oblique" — gimbal tilts to 3 angles
    # per pass for richer photogrammetry.  M4E ONLY.  M4T falls through with 0.
    if quick_ortho_mapping_pitch is not None:
        kml.append('  <wpml:quickOrthoMappingEnable>1</wpml:quickOrthoMappingEnable>')
        kml.append(f'  <wpml:quickOrthoMappingPitch>{quick_ortho_mapping_pitch}</wpml:quickOrthoMappingPitch>')
    else:
        kml.append('  <wpml:quickOrthoMappingEnable>0</wpml:quickOrthoMappingEnable>')
    # shootType=distance: drone fires shutter at fixed ground-distance intervals
    # computed from overlap + height.  Replaces the previous startRecord (video).
    kml.append('  <wpml:shootType>distance</wpml:shootType>')
    kml.append('  <wpml:direction>0</wpml:direction>')
    kml.append('  <wpml:margin>0</wpml:margin>')

    # Payload param: multi-lens capture (wide + thermal).
    kml.append('  <wpml:payloadParam>')
    kml.append('    <wpml:payloadPositionIndex>0</wpml:payloadPositionIndex>')
    kml.append('    <wpml:focusMode>firstPoint</wpml:focusMode>')
    kml.append('    <wpml:meteringMode>average</wpml:meteringMode>')
    kml.append('    <wpml:dewarpingEnable>0</wpml:dewarpingEnable>')
    kml.append('    <wpml:returnMode>goHomeWithGimbalDown</wpml:returnMode>')
    kml.append('    <wpml:useGlobalPayloadLensIndex>0</wpml:useGlobalPayloadLensIndex>')
    kml.append(f'    <wpml:imageFormat>{payload_lens_index}</wpml:imageFormat>')
    kml.append('  </wpml:payloadParam>')

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
    """Generate a Pass 1 thermal grid KMZ as a DJI mapping2d mission for M4T.

    Replaces the prior hand-rolled lawnmower (`templateType=waypoint` +
    `startRecord` video) with a native DJI mapping2d template:
      - drone computes optimal grid from polygon + altitude + overlap
      - `surfaceFollowModeEnable=1` keeps constant AGL over rolling terrain
      - `shootType=distance` fires interval stills (replaces video)
      - `imageFormat=wide,ir` captures both lenses on every shot
      - `gimbalRotate` to -90° before survey starts

    Output structure: `wpmz/template.kml` (DJI's canonical KMZ layout for
    template missions; Pilot 2 generates waylines on import).
    """
    kml_data = parse_kml(kml_path)
    if not kml_data["polygons"]:
        raise ValueError(f"No polygons found in {kml_path}")
    polygon = kml_data["polygons"][0]

    template_kml = _mapping2d_template_kml(
        polygon=polygon,
        altitude_m=altitude_m,
        speed_ms=speed_ms,
        overlap_pct=overlap_pct,
        drone_sub_enum=M4T_DRONE_SUB_ENUM,
        payload_enum=M4T_PAYLOAD_ENUM,
        payload_lens_index='wide,ir',
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as kmz:
        kmz.writestr('wpmz/template.kml', template_kml)
    kmz_bytes = buf.getvalue()

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(kmz_bytes)
        print(f"Pass 1 mapping2d KMZ saved to {out}")
        print(f"  Survey polygon: {len(polygon)} vertices")
        print(f"  Surface-follow altitude: {altitude_m:.0f}m AGL")
        print(f"  Overlap: {int(overlap_pct * 100)}% (drone computes grid)")
        print(f"  Capture: wide + thermal (R-JPEG via drone settings)")

    return kmz_bytes


def run(
    detections_path: str,
    obstacles_path: str,
    output_path: str,
    resolutions_path: str | None = None,
    mission_id: str | None = None,
    property_id: str | None = None,
):
    with open(detections_path) as f:
        detection_data = json.load(f)

    clusters = detection_data['clusters']
    cowans = load_cowans(obstacles_path) if obstacles_path else []

    # Infer mission_id from the detections file when not given, so the
    # legacy data/resolutions/{mission_id}.json path can be found.
    if mission_id is None:
        mission_id = detection_data.get('mission_id')
    if property_id is None:
        property_id = detection_data.get('property_id')

    resolutions = load_resolutions(
        resolutions_path=resolutions_path,
        mission_id=mission_id,
        property_id=property_id,
    )
    if not resolutions:
        print(
            "  NOTE: no operator resolutions found — any cluster near a "
            "LOW-confidence obstacle will be EXCLUDED from the KMZ "
            "(conservative default). Resolve obstacles in the companion app first."
        )

    print(f"Generating Pass 2 waypoints for {len(clusters)} clusters...")
    waypoints, excluded = plan_waypoints(clusters, cowans, resolutions)
    kml_content = build_kml(clusters, cowans, resolutions)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(str(out), 'w', zipfile.ZIP_DEFLATED) as kmz:
        kmz.writestr('waylines.wpml', kml_content)

    print(f"Pass 2 waypoints saved to {out}")
    print(f"  {len(waypoints)} flyable waypoint(s), {len(excluded)} excluded by safety locks")
    print(f"Load into DJI Pilot 2 -> Route Mission -> Import KMZ")

    for wp in waypoints:
        print(f"  WP{wp['index']+1}: {wp['lat']:.5f},{wp['lon']:.5f} "
              f"alt={wp['alt_m']:.0f}m count={wp['count']} conf={wp['confidence']}")
    for ex in excluded:
        print(f"  LOCKED (not in KMZ): {ex['lat']:.5f},{ex['lon']:.5f} — {ex['lock_reason']}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--detections', required=True)
    parser.add_argument('--obstacles', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--resolutions', default=None,
                        help='Path to resolutions JSON (default: auto-discover from '
                             'data/properties/{property_id}/resolutions.json or '
                             'data/resolutions/{mission_id}.json)')
    parser.add_argument('--mission-id', default=None,
                        help='Mission ID for resolutions lookup (default: from detections JSON)')
    parser.add_argument('--property-id', default=None,
                        help='Property ID for resolutions lookup (default: from detections JSON)')
    args = parser.parse_args()
    run(
        args.detections, args.obstacles, args.output,
        resolutions_path=args.resolutions,
        mission_id=args.mission_id,
        property_id=args.property_id,
    )
