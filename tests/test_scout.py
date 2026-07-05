"""Tests for Phase 1.5c — M4E Outer Guard scout module.

Covers:
- scout_kmz_generator emits M4E mapping2d KMZ with Smart Oblique
- scout_processor pipeline runs in mock mode (no ONNX model)
- Cowan cache persistence + freshness check

Hardware-only validation (excluded): real M4E imagery, EXIF-derived
GPS for individual hazards, Pilot 2 KMZ import.
"""
import io
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.scout_kmz_generator import (
    generate_scout_kmz,
    DEFAULT_OBLIQUE_PITCH_DEG,
)
from core.scout_processor import (
    is_scout_stale,
    load_cached_cowans,
    process_scout_imagery,
    SCOUT_FRESHNESS_DAYS,
)
from core.waypoint_generator import M4E_DRONE_SUB_ENUM, M4E_PAYLOAD_ENUM, M4T_DRONE_ENUM


WPML_NS = "http://www.dji.com/wpmz/1.0.6"
KML_NS = "http://www.opengis.net/kml/2.2"


def _ns(tag: str) -> str:
    return f"{{{WPML_NS}}}{tag}"


def _kml_ns(tag: str) -> str:
    return f"{{{KML_NS}}}{tag}"


SAMPLE_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <Placemark>
      <Polygon>
        <outerBoundaryIs>
          <LinearRing>
            <coordinates>
              -76.460,36.770,0
              -76.460,36.790,0
              -76.440,36.790,0
              -76.440,36.770,0
              -76.460,36.770,0
            </coordinates>
          </LinearRing>
        </outerBoundaryIs>
      </Polygon>
    </Placemark>
  </Document>
</kml>"""


def _kmz_to_template_kml(kmz_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(kmz_bytes)) as z:
        return z.read('wpmz/template.kml').decode('utf-8')


class _ScoutKmzBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.kml_path = Path(cls._tmpdir.name) / 'property.kml'
        cls.kml_path.write_text(SAMPLE_KML)
        cls.kmz_bytes = generate_scout_kmz(str(cls.kml_path))
        cls.template_xml = _kmz_to_template_kml(cls.kmz_bytes)
        cls.root = ET.fromstring(cls.template_xml)

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()


class TestScoutKmzM4EConfig(_ScoutKmzBase):
    def test_drone_enum_is_m4e_not_m4t(self):
        drone_info = cls_root_find(self.root, _ns('droneInfo'))
        self.assertEqual(drone_info.find(_ns('droneEnumValue')).text, str(M4T_DRONE_ENUM),
                         "M4E and M4T share droneEnumValue=99")
        self.assertEqual(
            drone_info.find(_ns('droneSubEnumValue')).text, str(M4E_DRONE_SUB_ENUM),
            "M4E uses droneSubEnumValue=0; if this fails, scout is misrouted to M4T"
        )

    def test_payload_enum_is_m4e_rgb_camera(self):
        payload_info = cls_root_find(self.root, _ns('payloadInfo'))
        self.assertEqual(payload_info.find(_ns('payloadEnumValue')).text, str(M4E_PAYLOAD_ENUM))


class TestScoutSmartOblique(_ScoutKmzBase):
    def test_quick_ortho_mapping_enabled(self):
        folder = cls_root_find(self.root, _kml_ns('Folder'))
        self.assertEqual(
            folder.find(_ns('quickOrthoMappingEnable')).text, '1',
            "Smart Oblique Capture must be enabled for M4E Outer Guard"
        )

    def test_quick_ortho_pitch_in_valid_range(self):
        folder = cls_root_find(self.root, _kml_ns('Folder'))
        pitch = int(folder.find(_ns('quickOrthoMappingPitch')).text)
        self.assertEqual(pitch, DEFAULT_OBLIQUE_PITCH_DEG)
        self.assertGreaterEqual(pitch, 10, "WPML spec: pitch range [10, 30]")
        self.assertLessEqual(pitch, 30, "WPML spec: pitch range [10, 30]")

    def test_payload_lens_is_wide_only_no_thermal(self):
        payload = cls_root_find(self.root, _ns('payloadParam'))
        self.assertEqual(
            payload.find(_ns('imageFormat')).text, 'wide',
            "M4E has no thermal — must NOT include 'ir' in lens index"
        )

    def test_surface_follow_enabled_for_terrain(self):
        coord_param = cls_root_find(self.root, _ns('waylineCoordinateSysParam'))
        self.assertEqual(coord_param.find(_ns('surfaceFollowModeEnable')).text, '1')


class TestScoutKmzPolygonValidation(unittest.TestCase):
    def test_invalid_oblique_pitch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            kml_path = Path(tmp) / 'p.kml'
            kml_path.write_text(SAMPLE_KML)
            with self.assertRaises(ValueError):
                generate_scout_kmz(str(kml_path), oblique_pitch_deg=5)
            with self.assertRaises(ValueError):
                generate_scout_kmz(str(kml_path), oblique_pitch_deg=45)


class TestScoutProcessorMockMode(unittest.TestCase):
    """Exercise scout_processor without an ONNX model — visual_detector
    returns [] and the rest of the pipeline must still produce a valid record."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmpdir.name)
        self.images_dir = self.tmp / 'scout_images'
        self.images_dir.mkdir()
        # Touch a fake image so the directory is non-empty (visual_detector
        # bails to mock mode anyway when model_path is None).
        (self.images_dir / 'fake.jpg').write_bytes(b'\xff\xd8\xff\xd9')
        self.output_root = self.tmp / 'data' / 'properties'

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_pipeline_writes_cowan_cache_in_mock_mode(self):
        record = process_scout_imagery(
            property_id='demo',
            image_dir=str(self.images_dir),
            model_path=None,
            output_root=str(self.output_root),
        )
        self.assertEqual(record['property_id'], 'demo')
        self.assertEqual(record['cowan_count'], 0,
                         "Mock mode (no ONNX model) yields zero detections")
        self.assertEqual(record['image_count'], 1)
        self.assertTrue(Path(record['output_path']).is_file())
        self.assertEqual(
            Path(record['output_path']).name, 'obstacles.json',
            "Scout must persist to obstacles.json — the file the API serves "
            "(cowans.json was never read by api/server.py)"
        )

    def test_legacy_cowans_json_still_loadable(self):
        """Back-compat: pre-2026-07-04 caches used cowans.json + 'cowans' key."""
        legacy_dir = self.output_root / 'legacy_prop'
        legacy_dir.mkdir(parents=True)
        (legacy_dir / 'cowans.json').write_text(json.dumps({
            'property_id': 'legacy_prop',
            'last_scouted': '2026-01-01T00:00:00+00:00',
            'cowans': [{'id': 'x', 'type': 'tower'}],
        }))
        loaded = load_cached_cowans('legacy_prop', root=str(self.output_root))
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded['obstacles']), 1)

    def test_persisted_record_loadable(self):
        process_scout_imagery(
            property_id='demo',
            image_dir=str(self.images_dir),
            model_path=None,
            output_root=str(self.output_root),
        )
        loaded = load_cached_cowans('demo', root=str(self.output_root))
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded['property_id'], 'demo')
        self.assertIn('last_scouted', loaded)
        self.assertIsInstance(loaded['obstacles'], list)

    def test_persisted_record_has_no_internal_fields(self):
        process_scout_imagery(
            property_id='demo',
            image_dir=str(self.images_dir),
            model_path=None,
            output_root=str(self.output_root),
        )
        loaded = load_cached_cowans('demo', root=str(self.output_root))
        for cowan in loaded['obstacles']:
            for key in cowan:
                self.assertFalse(
                    key.startswith('_'),
                    f"Internal field {key} leaked into persisted JSON"
                )


class TestScoutFreshness(unittest.TestCase):
    def test_missing_record_is_stale(self):
        self.assertTrue(is_scout_stale(None))
        self.assertTrue(is_scout_stale({}))

    def test_recent_record_not_stale(self):
        record = {'last_scouted': datetime.now(timezone.utc).isoformat()}
        self.assertFalse(is_scout_stale(record))

    def test_old_record_is_stale(self):
        old = datetime.now(timezone.utc) - timedelta(days=SCOUT_FRESHNESS_DAYS + 30)
        record = {'last_scouted': old.isoformat()}
        self.assertTrue(is_scout_stale(record))

    def test_load_returns_none_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(load_cached_cowans('does_not_exist', root=tmp))


def cls_root_find(root, tag):
    """Helper — etree's findall doesn't navigate generic descendants without
    './/' prefix.  This wraps that idiom for terser test code."""
    return root.find(f".//{tag}")


if __name__ == '__main__':
    unittest.main()
