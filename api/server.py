"""
Herd Mapper API server.

Reads Pass 1 pipeline output from data/ and serves it to the companion app.
Also serves the compiled React build so one URL covers everything.

Usage (development — companion app on Vite):
    uvicorn api.server:app --reload --port 8000

Usage (field deployment):
    cd companion_app && npm run build
    uvicorn api.server:app --host 0.0.0.0 --port 8000
    # Operator opens http://<LAPTOP_IP>:8000 on RC Pro browser
"""

import json
import math
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))

# SHARED safety logic — the exact same functions compute the altitude the
# operator sees here and the executeHeight written into the flown KMZ by
# core/waypoint_generator.py.  Never fork these calculations locally.
from core.outer_guard import (
    get_safe_altitude,
    get_waypoint_lock,
    SAFETY_BUFFER_M,
    SAFE_ALT_EXTRA_MARGIN_M,
    MIN_SAFE_ALT_M,
)

DATA_DIR  = Path(__file__).parent.parent / 'data'
BUILD_DIR = Path(__file__).parent.parent / 'companion_app' / 'dist'

DEG_PER_M_LAT    = 1 / 111320

app = FastAPI(title='Herd Mapper API', version='1.1.0')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['GET', 'POST'],
    allow_headers=['*'],
)


# ── helpers ──────────────────────────────────────────────────────────────────

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        # A truncated/corrupt file must not 500 every endpoint forever.
        print(f"WARNING: corrupt JSON at {path}: {exc} — treating as missing")
        return None


def load_mission_config(mission_id: str) -> dict:
    path = DATA_DIR / 'missions' / mission_id / 'config.json'
    return load_json(path) or {}


def load_property_obstacles(property_id: str) -> list | None:
    path = DATA_DIR / 'properties' / property_id / 'obstacles.json'
    data = load_json(path)
    if data is None:
        # Back-compat: scout_processor wrote cowans.json before 2026-07-04
        data = load_json(DATA_DIR / 'properties' / property_id / 'cowans.json')
    if data is None:
        return None
    if isinstance(data, list):
        return data
    return data.get('obstacles', data.get('cowans', []))


def load_property_bounds(property_id: str) -> dict | None:
    return load_json(DATA_DIR / 'properties' / property_id / 'bounds.json')


def load_property_lake(property_id: str) -> dict | None:
    return load_json(DATA_DIR / 'properties' / property_id / 'lake.json')


def load_resolutions(mission_id: str, property_id: str | None = None) -> dict:
    # Property-level resolutions take precedence (persistent across missions)
    if property_id:
        path = DATA_DIR / 'properties' / property_id / 'resolutions.json'
        data = load_json(path)
        if data is not None:
            return data
    # Fallback: legacy mission-scoped resolutions
    path = DATA_DIR / 'resolutions' / f'{mission_id}.json'
    return load_json(path) or {}


def _write_json_atomic(path: Path, payload) -> None:
    """Write JSON via temp file + atomic rename — a crash mid-write must
    never leave truncated safety data (same pattern as pipeline_runner)."""
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w') as f:
        json.dump(payload, f, indent=2)
    tmp.replace(path)


def save_resolutions(mission_id: str, resolutions: dict, property_id: str | None = None):
    if property_id:
        path = DATA_DIR / 'properties' / property_id
        path.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(path / 'resolutions.json', resolutions)
    else:
        path = DATA_DIR / 'resolutions'
        path.mkdir(parents=True, exist_ok=True)
        _write_json_atomic(path / f'{mission_id}.json', resolutions)


def derive_waypoints(clusters: list, obstacles: list, resolutions: dict) -> list:
    """
    For each cluster, determine Pass 2 safe altitude and locked state.
    A waypoint is locked if any LOW confidence obstacle (not yet resolved safe)
    has its exclusion zone overlapping the cluster position.

    Both calculations delegate to core.outer_guard so the values shown
    here are IDENTICAL to what waypoint_generator writes into the KMZ.
    """
    waypoints = []

    for i, c in enumerate(clusters):
        safe_alt = get_safe_altitude(c['lat'], c['lon'], obstacles)
        locked_by, lock_reason = get_waypoint_lock(c['lat'], c['lon'], obstacles, resolutions)

        waypoints.append({
            'id':          c['id'],
            'index':       i + 1,
            'lat':         c['lat'],
            'lon':         c['lon'],
            'count':       c['count'],
            'confidence':  c['confidence'],
            'label':       c.get('label', ''),
            'safe_alt_m':  safe_alt,
            'locked':      locked_by is not None,
            'locked_by':   locked_by,
            'lock_reason': lock_reason,
        })

    return waypoints


def format_bounds(bounds_raw: dict) -> dict:
    return {
        'center': [bounds_raw['center_lat'], bounds_raw['center_lon']],
        'north':   bounds_raw['north'],
        'south':   bounds_raw['south'],
        'east':    bounds_raw['east'],
        'west':    bounds_raw['west'],
        'name':    bounds_raw.get('name', ''),
    }


def format_lake(lake_raw: dict | None) -> dict | None:
    if not lake_raw:
        return None
    return {
        'center':   [lake_raw['center_lat'], lake_raw['center_lon']],
        'radius_m':  lake_raw['radius_m'],
        'label':     lake_raw.get('label', 'Water'),
    }


def build_scout_response(property_id: str) -> dict | None:
    """Scout mode: property bounds + obstacles, no detections or waypoints."""
    bounds_raw  = load_property_bounds(property_id)
    obstacles   = load_property_obstacles(property_id)
    lake_raw    = load_property_lake(property_id)

    if not bounds_raw or obstacles is None:
        return None

    resolutions = load_resolutions(property_id, property_id)

    # AGL range summary for the bottom panel (visual detections may carry
    # height_m=None — treat as 0 rather than crashing the scout view)
    heights = [o.get('height_m') or 0 for o in obstacles]
    agl_min = int(MIN_SAFE_ALT_M)
    agl_max = round(max(heights) + SAFETY_BUFFER_M + SAFE_ALT_EXTRA_MARGIN_M) if heights else int(MIN_SAFE_ALT_M)

    return {
        'mission_id':    f'{property_id}_scout',
        'property_id':   property_id,
        'mission_type':  'scout',
        'drone':         'M4E',
        'status':        'scout_complete',
        'bounds':        format_bounds(bounds_raw),
        'lake':          format_lake(lake_raw),
        'obstacles':     obstacles,
        'resolutions':   resolutions,
        'agl_range':     {'min_m': agl_min, 'max_m': agl_max},
        'obstacle_summary': _obstacle_summary(obstacles),
    }


def build_mission_response(mission_id: str) -> dict | None:
    config = load_mission_config(mission_id)
    property_id = config.get('property_id')

    # Load obstacles: property-level first, fallback to legacy path
    obstacles = None
    if property_id:
        obstacles = load_property_obstacles(property_id)
    if obstacles is None:
        obs_path = DATA_DIR / 'obstacles' / f'{mission_id}_obstacles.json'
        obs_data = load_json(obs_path)
        if obs_data:
            obstacles = obs_data if isinstance(obs_data, list) else obs_data.get('obstacles', [])

    # Load detections
    det_path   = DATA_DIR / 'missions' / mission_id / 'detections.json'
    detections = load_json(det_path)
    if detections is None:
        # Legacy path
        detections = load_json(DATA_DIR / 'detections' / f'{mission_id}_detections.json')

    if not detections or obstacles is None:
        return None

    # Load bounds + lake: property-level first, fallback to mission-level
    bounds_raw = None
    lake_raw   = None
    if property_id:
        bounds_raw = load_property_bounds(property_id)
        lake_raw   = load_property_lake(property_id)
    if bounds_raw is None:
        bounds_raw = load_json(DATA_DIR / 'missions' / mission_id / 'bounds.json')
        lake_raw   = load_json(DATA_DIR / 'missions' / mission_id / 'lake.json')

    if not bounds_raw:
        return None

    resolutions = load_resolutions(mission_id, property_id)
    clusters    = detections['clusters']
    waypoints   = derive_waypoints(clusters, obstacles, resolutions)

    return {
        'mission_id':   mission_id,
        'property_id':  property_id,
        'mission_type': config.get('mission_type', 'census'),
        'drone':        config.get('drone', 'M4T'),
        'status':       'pass1_complete',
        'pass1_agl_ft': detections.get('pass1_agl_ft', 200),
        'total_blobs':  detections.get('total_blobs', len(clusters)),
        'bounds':       format_bounds(bounds_raw),
        'lake':         format_lake(lake_raw),
        'clusters':     clusters,
        'obstacles':    obstacles,
        'waypoints':    waypoints,
        'resolutions':  resolutions,
    }


def _obstacle_summary(obstacles: list) -> dict:
    summary = {}
    for o in obstacles:
        summary[o['type']] = summary.get(o['type'], 0) + 1
    return summary


# ── routes ───────────────────────────────────────────────────────────────────

@app.get('/api/scout/{property_id}')
def get_scout(property_id: str):
    data = build_scout_response(property_id)
    if data is None:
        raise HTTPException(404, f"Property '{property_id}' not found — run: python core/mock_data.py --mode scout")
    return data


@app.get('/api/mission')
def get_mission(id: str = 'demo'):
    data = build_mission_response(id)
    if data is None:
        raise HTTPException(404, f"Mission '{id}' not found — run core/mock_data.py first")
    return data


@app.get('/api/mission/{mission_id}')
def get_mission_by_id(mission_id: str):
    data = build_mission_response(mission_id)
    if data is None:
        raise HTTPException(404, f"Mission '{mission_id}' not found")
    return data


class ResolveRequest(BaseModel):
    obstacle_id: str
    decision: str              # 'safe' | 'hazard'
    mission_id: Optional[str] = 'demo'
    property_id: Optional[str] = None


@app.post('/api/resolve')
def resolve_obstacle(req: ResolveRequest):
    if req.decision not in ('safe', 'hazard'):
        raise HTTPException(400, "decision must be 'safe' or 'hazard'")

    # Determine property_id: from request, or from mission config
    property_id = req.property_id
    if not property_id and req.mission_id:
        config = load_mission_config(req.mission_id)
        property_id = config.get('property_id')

    resolutions = load_resolutions(req.mission_id, property_id)
    resolutions[req.obstacle_id] = req.decision
    save_resolutions(req.mission_id, resolutions, property_id)

    # Return updated waypoints for census missions; empty list for scout
    data = build_mission_response(req.mission_id) if req.mission_id else None
    return {'ok': True, 'waypoints': data['waypoints'] if data else []}


@app.get('/api/health')
def health():
    return {'status': 'ok', 'data_dir': str(DATA_DIR), 'data_exists': DATA_DIR.exists()}


# ── static serving (field deployment) ────────────────────────────────────────

if BUILD_DIR.exists():
    app.mount('/assets', StaticFiles(directory=BUILD_DIR / 'assets'), name='assets')

    @app.get('/{full_path:path}')
    def serve_spa(full_path: str):
        if full_path.startswith('api/'):
            raise HTTPException(404, f"API route '/{full_path}' not found")
        index = BUILD_DIR / 'index.html'
        if index.exists():
            return FileResponse(index)
        raise HTTPException(404, 'React build not found — run: cd companion_app && npm run build')
