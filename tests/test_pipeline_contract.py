"""Cross-module contract + flight-safety tests (2026-07-04 review fixes).

These are the tests whose absence let the watch-folder pipeline ship broken:

1. pipeline_runner writes detections.json in EXACTLY the schema
   api/server.py and derive_waypoints consume (dict with 'clusters',
   each cluster carrying id/lat/lon/count/confidence).
2. get_safe_altitude honors per-Cowan exclusion_radius_m (guy-wire cones
   larger than the baseline search radius must still raise altitude), and
   the UI (api/server.py) and KMZ (waypoint_generator) use the SAME shared
   function — values must be identical.
3. build_kml excludes clusters locked by unresolved / hazard-confirmed
   LOW-confidence obstacles, matching the companion-app lock rule.
"""
import json
import math
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

from core.outer_guard import (
    Cowan,
    get_safe_altitude,
    get_waypoint_lock,
    MIN_SAFE_ALT_M,
    SAFETY_BUFFER_M,
    SAFE_ALT_EXTRA_MARGIN_M,
)
from core.waypoint_generator import build_kml, plan_waypoints
from api.server import derive_waypoints

import core.pipeline_runner as pipeline_runner


KML_NS = "http://www.opengis.net/kml/2.2"
WPML_NS = "http://www.dji.com/wpmz/1.0.6"

BASE_LAT = 36.7821
BASE_LON = -76.4523
DEG_PER_M_LAT = 1 / 111320


def _offset_lat(meters: float) -> float:
    return BASE_LAT + meters * DEG_PER_M_LAT


# ── 1. pipeline → API schema contract ────────────────────────────────────────

class TestPipelineDetectionsSchema(unittest.TestCase):
    """MissionProcessor must write detections.json the API can serve."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old_cwd = os.getcwd()
        os.chdir(self._tmpdir.name)  # MissionProcessor uses relative data/ paths

    def tearDown(self):
        os.chdir(self._old_cwd)
        self._tmpdir.cleanup()

    @staticmethod
    def _fake_geo_blobs(image_path: str):
        """Synthetic detect_blobs_geo output: two blobs 5m apart (one cluster)."""
        return [
            {'pixel_x': 100.0, 'pixel_y': 100.0, 'area_px': 50, 'confidence': 'HIGH',
             'lat': BASE_LAT, 'lon': BASE_LON, 'source_image': Path(image_path).name},
            {'pixel_x': 110.0, 'pixel_y': 100.0, 'area_px': 20, 'confidence': 'MEDIUM',
             'lat': _offset_lat(5), 'lon': BASE_LON, 'source_image': Path(image_path).name},
        ]

    def _run_pipeline_once(self):
        incoming = Path('data/incoming/testmission')
        incoming.mkdir(parents=True)
        img = incoming / 'DJI_0001_T.JPG'
        img.write_bytes(b'\xff\xd8\xff\xd9')  # fake JPEG

        with mock.patch.object(pipeline_runner, 'detect_blobs_geo',
                               side_effect=self._fake_geo_blobs):
            proc = pipeline_runner.MissionProcessor('testmission')
            proc.accept_image(img)
            proc.finalize()
        return Path('data/missions/testmission')

    def test_detections_json_is_dict_with_clusters(self):
        mission_dir = self._run_pipeline_once()
        with open(mission_dir / 'detections.json') as f:
            detections = json.load(f)

        self.assertIsInstance(
            detections, dict,
            "detections.json must be a dict (server.py reads detections['clusters']); "
            "a raw list 404s or 500s every /api/mission call"
        )
        self.assertIn('clusters', detections)
        self.assertIn('total_blobs', detections)
        self.assertEqual(detections['total_blobs'], 2)
        self.assertEqual(len(detections['clusters']), 1,
                         "Two blobs 5m apart must merge into one cluster")

        for cluster in detections['clusters']:
            for key in ('id', 'lat', 'lon', 'count', 'confidence'):
                self.assertIn(key, cluster,
                              f"cluster missing '{key}' — derive_waypoints requires it")

    def test_pipeline_clusters_feed_derive_waypoints(self):
        """The API's waypoint derivation must accept pipeline output as-is."""
        mission_dir = self._run_pipeline_once()
        with open(mission_dir / 'detections.json') as f:
            detections = json.load(f)

        obstacles = [{
            'id': 'tower_0', 'lat': _offset_lat(200), 'lon': BASE_LON,
            'height_m': 22.0, 'type': 'tower', 'confidence': 'LOW',
            'exclusion_radius_m': 33.0,
        }]
        waypoints = derive_waypoints(detections['clusters'], obstacles, {})
        self.assertEqual(len(waypoints), 1)
        for key in ('id', 'lat', 'lon', 'safe_alt_m', 'locked'):
            self.assertIn(key, waypoints[0])

    def test_status_json_has_error_field(self):
        mission_dir = self._run_pipeline_once()
        with open(mission_dir / 'status.json') as f:
            status = json.load(f)
        self.assertIn('error', status,
                      "status.json must carry an error flag so import/detection "
                      "failures are never silent")
        self.assertIsNone(status['error'])
        self.assertEqual(status['status'], 'pass1_complete')


# ── 2. safe altitude honors exclusion radii + UI/KMZ parity ─────────────────

class TestSafeAltitudeExclusionRadius(unittest.TestCase):
    def test_tower_cone_beyond_search_radius_still_counts(self):
        """A 40m tower has a 60m guy-wire cone; a cluster 55m away sits
        INSIDE the cone but outside the old fixed 50m search radius.  It
        must get a cleared altitude, not the 15m default."""
        tower = Cowan(id='tower_0', lat=_offset_lat(55), lon=BASE_LON,
                      height_m=40.0, type='tower', confidence='LOW',
                      exclusion_radius_m=60.0)
        alt = get_safe_altitude(BASE_LAT, BASE_LON, [tower])
        expected = round(40.0 + SAFETY_BUFFER_M + SAFE_ALT_EXTRA_MARGIN_M)
        self.assertEqual(alt, expected,
                         f"Waypoint inside a guy-wire cone got {alt}m — must clear "
                         f"the tower ({expected}m), never descend to 15m in the cone")

    def test_far_obstacle_outside_both_radii_ignored(self):
        far = Cowan(id='pole_0', lat=_offset_lat(120), lon=BASE_LON,
                    height_m=10.0, type='fence_line', confidence='MEDIUM',
                    exclusion_radius_m=5.0)
        self.assertEqual(get_safe_altitude(BASE_LAT, BASE_LON, [far]), MIN_SAFE_ALT_M)

    def test_dicts_and_dataclasses_give_identical_results(self):
        as_dataclass = [Cowan(id='t', lat=_offset_lat(30), lon=BASE_LON,
                              height_m=20.0, type='tower', confidence='LOW',
                              exclusion_radius_m=30.0)]
        as_dict = [{'id': 't', 'lat': _offset_lat(30), 'lon': BASE_LON,
                    'height_m': 20.0, 'type': 'tower', 'confidence': 'LOW',
                    'exclusion_radius_m': 30.0}]
        self.assertEqual(
            get_safe_altitude(BASE_LAT, BASE_LON, as_dataclass),
            get_safe_altitude(BASE_LAT, BASE_LON, as_dict),
        )

    def test_ui_and_kmz_altitudes_identical(self):
        """The altitude the operator approves in the companion app must be
        the altitude the drone flies.  Same cluster + obstacles through
        api.server.derive_waypoints (UI) and build_kml (KMZ)."""
        cluster = {'id': 'cluster_001', 'lat': BASE_LAT, 'lon': BASE_LON,
                   'count': 5, 'confidence': 'HIGH', 'label': ''}
        obs_dict = [{'id': 'tower_0', 'lat': _offset_lat(55), 'lon': BASE_LON,
                     'height_m': 40.0, 'type': 'tower', 'confidence': 'LOW',
                     'exclusion_radius_m': 60.0}]
        obs_cowan = [Cowan(**o) for o in obs_dict]
        resolutions = {'tower_0': 'safe'}  # unlocked so the KMZ includes it

        ui_wp = derive_waypoints([cluster], obs_dict, resolutions)[0]
        self.assertFalse(ui_wp['locked'])

        kml_text = build_kml([cluster], obs_cowan, resolutions)
        root = ET.fromstring(kml_text)
        exec_heights = root.findall(f".//{{{WPML_NS}}}executeHeight")
        self.assertEqual(len(exec_heights), 1)
        self.assertEqual(
            float(exec_heights[0].text), float(ui_wp['safe_alt_m']),
            "UI-displayed and KMZ-flown altitudes DIVERGED — safe-altitude "
            "logic must stay in the single shared core.outer_guard function"
        )


# ── 3. KMZ honors operator locks / resolutions ───────────────────────────────

class TestKmzHonorsLocks(unittest.TestCase):
    def setUp(self):
        self.cluster = {'id': 'cluster_001', 'lat': BASE_LAT, 'lon': BASE_LON,
                        'count': 5, 'confidence': 'HIGH', 'label': ''}
        # LOW-confidence tower whose exclusion zone (+20m approach buffer)
        # covers the cluster: 30m away, 33m exclusion radius.
        self.tower = Cowan(id='tower_0', lat=_offset_lat(30), lon=BASE_LON,
                           height_m=22.0, type='tower', confidence='LOW',
                           exclusion_radius_m=33.0)

    def _placemark_count(self, kml_text: str) -> int:
        root = ET.fromstring(kml_text)
        return len(root.findall(f".//{{{KML_NS}}}Placemark"))

    def test_unresolved_low_obstacle_excludes_cluster(self):
        kml_text = build_kml([self.cluster], [self.tower], resolutions={})
        self.assertEqual(self._placemark_count(kml_text), 0,
                         "Cluster locked by an UNRESOLVED LOW-confidence obstacle "
                         "must NOT be flown — the UI shows it locked")

    def test_no_resolutions_defaults_conservative(self):
        kml_text = build_kml([self.cluster], [self.tower])  # resolutions=None
        self.assertEqual(self._placemark_count(kml_text), 0)

    def test_hazard_confirmed_stays_excluded(self):
        kml_text = build_kml([self.cluster], [self.tower],
                             resolutions={'tower_0': 'hazard'})
        self.assertEqual(self._placemark_count(kml_text), 0,
                         "Operator confirmed HAZARD — the drone must never be "
                         "routed there regardless of CLI usage")

    def test_resolved_safe_is_included(self):
        kml_text = build_kml([self.cluster], [self.tower],
                             resolutions={'tower_0': 'safe'})
        self.assertEqual(self._placemark_count(kml_text), 1)

    def test_kmz_lock_rule_matches_server_lock_rule(self):
        """plan_waypoints and derive_waypoints must agree on locking for
        the same inputs (shared get_waypoint_lock)."""
        obs_dict = [{'id': 'tower_0', 'lat': _offset_lat(30), 'lon': BASE_LON,
                     'height_m': 22.0, 'type': 'tower', 'confidence': 'LOW',
                     'exclusion_radius_m': 33.0}]
        for resolutions in ({}, {'tower_0': 'hazard'}, {'tower_0': 'safe'}):
            ui_wp = derive_waypoints([self.cluster], obs_dict, resolutions)[0]
            flyable, excluded = plan_waypoints([self.cluster], [self.tower], resolutions)
            self.assertEqual(
                ui_wp['locked'], len(excluded) == 1,
                f"UI lock and KMZ exclusion disagree for resolutions={resolutions}"
            )

    def test_partial_exclusion_keeps_other_waypoints(self):
        far_cluster = {'id': 'cluster_002', 'lat': _offset_lat(400), 'lon': BASE_LON,
                       'count': 3, 'confidence': 'MEDIUM', 'label': ''}
        kml_text = build_kml([self.cluster, far_cluster], [self.tower], resolutions={})
        self.assertEqual(self._placemark_count(kml_text), 1,
                         "Only the locked cluster is excluded; the safe one flies")


if __name__ == '__main__':
    unittest.main()
