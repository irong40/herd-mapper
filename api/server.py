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
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

DATA_DIR  = Path(__file__).parent.parent / 'data'
BUILD_DIR = Path(__file__).parent.parent / 'companion_app' / 'dist'

SAFETY_BUFFER_M  = 8.0
DEG_PER_M_LAT    = 1 / 111320

app = FastAPI(title='Herd Mapper API', version='1.0.0')

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
    with open(path) as f:
        return json.load(f)


def load_resolutions(mission_id: str) -> dict:
    path = DATA_DIR / 'resolutions' / f'{mission_id}.json'
    return load_json(path) or {}


def save_resolutions(mission_id: str, resolutions: dict):
    path = DATA_DIR / 'resolutions'
    path.mkdir(parents=True, exist_ok=True)
    with open(path / f'{mission_id}.json', 'w') as f:
        json.dump(resolutions, f, indent=2)


def derive_waypoints(clusters: list, obstacles: list, resolutions: dict) -> list:
    """
    For each cluster, determine Pass 2 safe altitude and locked state.
    A waypoint is locked if any LOW confidence obstacle (not yet resolved safe)
    has its exclusion zone overlapping the cluster position.
    """
    low_obs = [o for o in obstacles if o['confidence'] == 'LOW']
    waypoints = []

    for i, c in enumerate(clusters):
        # Max obstacle height within 60m radius (for safe altitude calc)
        nearby_heights = [
            o['height_m']
            for o in obstacles
            if haversine_m(c['lat'], c['lon'], o['lat'], o['lon']) < 60
        ]
        max_h = max(nearby_heights) if nearby_heights else 0
        safe_alt = max(15, round(max_h + SAFETY_BUFFER_M + 5))

        # Check for unresolved LOW confidence obstacle overlap
        locked_by = None
        lock_reason = None
        for o in low_obs:
            dist = haversine_m(c['lat'], c['lon'], o['lat'], o['lon'])
            if dist < o['exclusion_radius_m'] + 20:  # 20m approach buffer
                if resolutions.get(o['id']) != 'safe':
                    locked_by = o['id']
                    lock_reason = f"{'Confirmed hazard' if resolutions.get(o['id']) == 'hazard' else 'Unresolved'} obstacle nearby ({o['id']})"
                    break

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


def build_mission_response(mission_id: str) -> dict:
    det_path  = DATA_DIR / 'detections' / f'{mission_id}_detections.json'
    obs_path  = DATA_DIR / 'obstacles'  / f'{mission_id}_obstacles.json'
    bnd_path  = DATA_DIR / 'missions'   / mission_id / 'bounds.json'
    lake_path = DATA_DIR / 'missions'   / mission_id / 'lake.json'

    detections = load_json(det_path)
    obs_data   = load_json(obs_path)
    bounds_raw = load_json(bnd_path)
    lake_raw   = load_json(lake_path)

    if not detections or not obs_data or not bounds_raw:
        return None

    resolutions = load_resolutions(mission_id)
    clusters    = detections['clusters']
    obstacles   = obs_data if isinstance(obs_data, list) else obs_data.get('obstacles', [])
    waypoints   = derive_waypoints(clusters, obstacles, resolutions)

    bounds = {
        'center':  [bounds_raw['center_lat'], bounds_raw['center_lon']],
        'north':    bounds_raw['north'],
        'south':    bounds_raw['south'],
        'east':     bounds_raw['east'],
        'west':     bounds_raw['west'],
        'name':     bounds_raw.get('name', mission_id),
    }

    lake = None
    if lake_raw:
        lake = {
            'center':   [lake_raw['center_lat'], lake_raw['center_lon']],
            'radius_m':  lake_raw['radius_m'],
            'label':     lake_raw.get('label', 'Water'),
        }

    return {
        'mission_id':   mission_id,
        'status':       'pass1_complete',
        'pass1_agl_ft': detections.get('pass1_agl_ft', 200),
        'total_blobs':  detections.get('total_blobs', len(clusters)),
        'bounds':       bounds,
        'lake':         lake,
        'clusters':     clusters,
        'obstacles':    obstacles,
        'waypoints':    waypoints,
        'resolutions':  resolutions,
    }


# ── routes ───────────────────────────────────────────────────────────────────

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
    decision: str   # 'safe' | 'hazard'
    mission_id: Optional[str] = 'demo'


@app.post('/api/resolve')
def resolve_obstacle(req: ResolveRequest):
    if req.decision not in ('safe', 'hazard'):
        raise HTTPException(400, "decision must be 'safe' or 'hazard'")
    resolutions = load_resolutions(req.mission_id)
    resolutions[req.obstacle_id] = req.decision
    save_resolutions(req.mission_id, resolutions)
    # Return updated waypoints so client can sync
    data = build_mission_response(req.mission_id)
    return {'ok': True, 'waypoints': data['waypoints'] if data else []}


@app.get('/api/health')
def health():
    return {'status': 'ok', 'data_dir': str(DATA_DIR), 'data_exists': DATA_DIR.exists()}


# ── static serving (field deployment) ────────────────────────────────────────

if BUILD_DIR.exists():
    app.mount('/assets', StaticFiles(directory=BUILD_DIR / 'assets'), name='assets')

    @app.get('/{full_path:path}')
    def serve_spa(full_path: str):
        # Serve index.html for all non-API routes (SPA routing)
        index = BUILD_DIR / 'index.html'
        if index.exists():
            return FileResponse(index)
        raise HTTPException(404, 'React build not found — run: cd companion_app && npm run build')
