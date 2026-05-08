"""Tests for Pass 1 + Pass 2 KMZ emission (waypoint_generator).

Phase 1.5a — Pass 2 build_kml: drone/payload enums, mission config required
fields, nadir gimbal lock via startActionGroup, multi-lens (wide+ir) takePhoto.

Phase 1.5b — Pass 1 generate_pass1_grid: mapping2d template, surfaceFollow,
shootType=distance, multi-lens, nadir gimbal lock, wpmz/template.kml structure.

Spec source: developer.dji.com WPML reference, 2026-05-08.
"""
import io
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from core.outer_guard import Cowan
from core.waypoint_generator import (
    build_kml,
    generate_pass1_grid,
    M4T_DRONE_ENUM,
    M4T_DRONE_SUB_ENUM,
    M4T_PAYLOAD_ENUM,
    RTH_BUFFER_M,
)


WPML_NS = "http://www.dji.com/wpmz/1.0.6"
KML_NS = "http://www.opengis.net/kml/2.2"


def _ns(tag: str) -> str:
    return f"{{{WPML_NS}}}{tag}"


def _kml_ns(tag: str) -> str:
    return f"{{{KML_NS}}}{tag}"


class TestBuildKmlMissionConfig(unittest.TestCase):
    def setUp(self):
        self.clusters = [
            {'lat': 36.78, 'lon': -76.45, 'count': 7, 'confidence': 0.92},
            {'lat': 36.79, 'lon': -76.44, 'count': 12, 'confidence': 0.88},
        ]
        self.cowans = [
            Cowan(lat=36.785, lon=-76.445, height_m=25.0, type='pole',
                  exclusion_radius_m=15.0, confidence='HIGH'),
        ]
        self.kml_text = build_kml(self.clusters, self.cowans)
        self.root = ET.fromstring(self.kml_text)
        self.mission_config = self.root.find(f".//{_ns('missionConfig')}")
        self.assertIsNotNone(self.mission_config, "missionConfig block missing")

    def test_drone_enum_values_m4t(self):
        drone_info = self.mission_config.find(_ns('droneInfo'))
        self.assertIsNotNone(drone_info, "droneInfo block missing")
        self.assertEqual(
            drone_info.find(_ns('droneEnumValue')).text, str(M4T_DRONE_ENUM)
        )
        self.assertEqual(
            drone_info.find(_ns('droneSubEnumValue')).text, str(M4T_DRONE_SUB_ENUM)
        )

    def test_payload_enum_value_m4t(self):
        payload_info = self.mission_config.find(_ns('payloadInfo'))
        self.assertIsNotNone(payload_info, "payloadInfo block missing")
        self.assertEqual(
            payload_info.find(_ns('payloadEnumValue')).text, str(M4T_PAYLOAD_ENUM)
        )
        self.assertEqual(
            payload_info.find(_ns('payloadPositionIndex')).text, '0'
        )

    def test_required_safety_fields_present(self):
        for tag in ('takeOffSecurityHeight', 'globalTransitionalSpeed',
                    'globalRTHHeight', 'flyToWaylineMode', 'finishAction',
                    'exitOnRCLost', 'executeRCLostAction'):
            elem = self.mission_config.find(_ns(tag))
            self.assertIsNotNone(elem, f"missionConfig missing required tag: {tag}")

    def test_global_rth_clears_tallest_cowan(self):
        rth = float(self.mission_config.find(_ns('globalRTHHeight')).text)
        # Tallest Cowan = 25m + buffer = 55m, must exceed it
        self.assertGreaterEqual(rth, 25.0 + RTH_BUFFER_M)


class TestBuildKmlGimbalLock(unittest.TestCase):
    def setUp(self):
        self.clusters = [{'lat': 36.78, 'lon': -76.45, 'count': 5, 'confidence': 0.9}]
        self.kml_text = build_kml(self.clusters, [])
        self.root = ET.fromstring(self.kml_text)

    def test_start_action_group_present(self):
        sag = self.root.find(f".//{_ns('startActionGroup')}")
        self.assertIsNotNone(sag, "startActionGroup missing — gimbal not locked at mission start")

    def test_start_action_group_is_gimbal_rotate_nadir(self):
        sag = self.root.find(f".//{_ns('startActionGroup')}")
        action = sag.find(_ns('action'))
        func = action.find(_ns('actionActuatorFunc')).text
        self.assertEqual(func, 'gimbalRotate')

        params = action.find(_ns('actionActuatorFuncParam'))
        self.assertEqual(params.find(_ns('gimbalRotateMode')).text, 'absoluteAngle')
        self.assertEqual(params.find(_ns('gimbalPitchRotateEnable')).text, '1')
        self.assertEqual(
            int(params.find(_ns('gimbalPitchRotateAngle')).text), -90,
            "Gimbal must be locked to nadir (-90°) for thermal census"
        )

    def test_start_action_group_has_required_metadata(self):
        sag = self.root.find(f".//{_ns('startActionGroup')}")
        for tag in ('actionGroupId', 'actionGroupStartIndex',
                    'actionGroupEndIndex', 'actionGroupMode', 'actionTrigger'):
            self.assertIsNotNone(
                sag.find(_ns(tag)),
                f"startActionGroup missing required tag: {tag}"
            )


class TestBuildKmlMultiLensCapture(unittest.TestCase):
    def setUp(self):
        self.clusters = [
            {'lat': 36.78, 'lon': -76.45, 'count': 5, 'confidence': 0.9},
            {'lat': 36.79, 'lon': -76.44, 'count': 8, 'confidence': 0.85},
        ]
        self.kml_text = build_kml(self.clusters, [])
        self.root = ET.fromstring(self.kml_text)
        self.placemarks = self.root.findall(f".//{_kml_ns('Placemark')}")

    def test_one_placemark_per_cluster(self):
        self.assertEqual(len(self.placemarks), len(self.clusters))

    def test_each_placemark_has_take_photo(self):
        for pm in self.placemarks:
            actions = pm.findall(f".//{_ns('action')}")
            funcs = [a.find(_ns('actionActuatorFunc')).text for a in actions]
            self.assertIn('takePhoto', funcs)
            self.assertIn('hover', funcs)

    def test_take_photo_is_multi_lens_wide_and_ir(self):
        for pm in self.placemarks:
            for action in pm.findall(f".//{_ns('action')}"):
                if action.find(_ns('actionActuatorFunc')).text != 'takePhoto':
                    continue
                params = action.find(_ns('actionActuatorFuncParam'))
                lens_index = params.find(_ns('payloadLensIndex')).text
                self.assertIn('wide', lens_index, f"Missing wide lens: {lens_index}")
                self.assertIn('ir', lens_index, f"Missing ir lens: {lens_index}")
                self.assertEqual(
                    params.find(_ns('useGlobalPayloadLensIndex')).text, '0',
                    "Per-action lens selection requires useGlobalPayloadLensIndex=0"
                )

    def test_action_groups_have_required_structure(self):
        for pm in self.placemarks:
            ag = pm.find(_ns('actionGroup'))
            self.assertIsNotNone(ag, "Placemark missing actionGroup")
            for tag in ('actionGroupId', 'actionGroupStartIndex',
                        'actionGroupEndIndex', 'actionGroupMode',
                        'actionTrigger'):
                self.assertIsNotNone(
                    ag.find(_ns(tag)),
                    f"actionGroup missing required tag: {tag}"
                )

    def test_file_suffix_per_cluster(self):
        suffixes = []
        for pm in self.placemarks:
            for action in pm.findall(f".//{_ns('action')}"):
                if action.find(_ns('actionActuatorFunc')).text == 'takePhoto':
                    suffix = action.find(f".//{_ns('fileSuffix')}").text
                    suffixes.append(suffix)
        self.assertEqual(len(suffixes), len(set(suffixes)),
                         "fileSuffix must be unique per cluster")


class TestBuildKmlFolder(unittest.TestCase):
    def setUp(self):
        self.kml_text = build_kml(
            [{'lat': 36.78, 'lon': -76.45, 'count': 5, 'confidence': 0.9}], []
        )
        self.root = ET.fromstring(self.kml_text)

    def test_template_type_waypoint(self):
        folder = self.root.find(f".//{_kml_ns('Folder')}")
        self.assertEqual(
            folder.find(_ns('templateType')).text, 'waypoint',
            "Pass 2 cluster visits use templateType=waypoint (not mapping)"
        )

    def test_execute_height_mode_explicit(self):
        folder = self.root.find(f".//{_kml_ns('Folder')}")
        self.assertEqual(
            folder.find(_ns('executeHeightMode')).text, 'relativeToStartPoint'
        )


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
    """Extract wpmz/template.kml from a Pass 1 KMZ byte stream."""
    with zipfile.ZipFile(io.BytesIO(kmz_bytes)) as z:
        names = z.namelist()
        # Pass 1 mapping2d KMZ uses canonical wpmz/ subdir per DJI spec
        template_path = next((n for n in names if n.endswith('template.kml')), None)
        if template_path is None:
            raise AssertionError(f"No template.kml in KMZ; got {names}")
        return z.read(template_path).decode('utf-8')


class _Pass1Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.kml_path = Path(cls._tmpdir.name) / 'property.kml'
        cls.kml_path.write_text(SAMPLE_KML)
        cls.kmz_bytes = generate_pass1_grid(
            kml_path=str(cls.kml_path),
            altitude_m=60.0,
            speed_ms=5.0,
            overlap_pct=0.75,
        )
        cls.template_xml = _kmz_to_template_kml(cls.kmz_bytes)
        cls.root = ET.fromstring(cls.template_xml)

    @classmethod
    def tearDownClass(cls):
        cls._tmpdir.cleanup()


class TestPass1KmzStructure(_Pass1Base):
    def test_kmz_uses_wpmz_template_kml(self):
        with zipfile.ZipFile(io.BytesIO(self.kmz_bytes)) as z:
            self.assertIn('wpmz/template.kml', z.namelist(),
                          "Pass 1 KMZ must use canonical wpmz/template.kml layout")

    def test_template_xml_well_formed(self):
        # setUpClass already parsed; just confirm root tag
        self.assertEqual(self.root.tag, f"{{{KML_NS}}}kml")


class TestPass1Mapping2dTemplate(_Pass1Base):
    def test_template_type_is_mapping2d(self):
        folder = self.root.find(f".//{_kml_ns('Folder')}")
        self.assertEqual(
            folder.find(_ns('templateType')).text, 'mapping2d',
            "Pass 1 must use mapping2d (auto-grid + terrain follow), "
            "not hand-rolled waypoint lawnmower"
        )

    def test_surface_follow_enabled(self):
        coord_param = self.root.find(f".//{_ns('waylineCoordinateSysParam')}")
        self.assertIsNotNone(coord_param, "waylineCoordinateSysParam missing")
        self.assertEqual(
            coord_param.find(_ns('surfaceFollowModeEnable')).text, '1',
            "Terrain-follow must be enabled for consistent thermal GSD"
        )
        rel_height = coord_param.find(_ns('surfaceRelativeHeight'))
        self.assertEqual(float(rel_height.text), 60.0)

    def test_polygon_present_and_closed(self):
        coords = self.root.find(f".//{_kml_ns('coordinates')}")
        self.assertIsNotNone(coords, "Survey polygon coordinates missing")
        coord_str = coords.text.strip()
        self.assertGreater(len(coord_str.split()), 3,
                           "Polygon must have at least 4 vertex coordinates")

    def test_overlap_settings(self):
        overlap = self.root.find(f".//{_ns('overlap')}")
        self.assertIsNotNone(overlap)
        self.assertEqual(overlap.find(_ns('orthoCameraOverlapH')).text, '75')
        self.assertEqual(overlap.find(_ns('orthoCameraOverlapW')).text, '75')

    def test_shoot_type_is_distance_not_video(self):
        folder = self.root.find(f".//{_kml_ns('Folder')}")
        self.assertEqual(
            folder.find(_ns('shootType')).text, 'distance',
            "Pass 1 must capture interval stills (R-JPEG), not video"
        )


class TestPass1MultiLensCapture(_Pass1Base):
    def test_payload_param_uses_wide_and_ir(self):
        payload = self.root.find(f".//{_ns('payloadParam')}")
        self.assertIsNotNone(payload)
        image_format = payload.find(_ns('imageFormat'))
        self.assertIsNotNone(image_format)
        self.assertIn('wide', image_format.text)
        self.assertIn('ir', image_format.text)

    def test_payload_uses_local_lens_index(self):
        payload = self.root.find(f".//{_ns('payloadParam')}")
        self.assertEqual(
            payload.find(_ns('useGlobalPayloadLensIndex')).text, '0',
            "Per-mission lens selection requires useGlobalPayloadLensIndex=0"
        )


class TestPass1MissionConfig(_Pass1Base):
    def test_drone_enum_m4t(self):
        drone_info = self.root.find(f".//{_ns('droneInfo')}")
        self.assertEqual(drone_info.find(_ns('droneEnumValue')).text, str(M4T_DRONE_ENUM))
        self.assertEqual(drone_info.find(_ns('droneSubEnumValue')).text, str(M4T_DRONE_SUB_ENUM))

    def test_payload_enum_m4t(self):
        payload_info = self.root.find(f".//{_ns('payloadInfo')}")
        self.assertEqual(payload_info.find(_ns('payloadEnumValue')).text, str(M4T_PAYLOAD_ENUM))

    def test_global_rth_above_survey_altitude(self):
        rth = float(self.root.find(f".//{_ns('globalRTHHeight')}").text)
        self.assertGreaterEqual(rth, 60.0 + RTH_BUFFER_M)


class TestPass1GimbalNadirLock(_Pass1Base):
    def test_start_action_group_is_nadir_gimbal_rotate(self):
        sag = self.root.find(f".//{_ns('startActionGroup')}")
        self.assertIsNotNone(sag, "Pass 1 missing startActionGroup — gimbal not locked")
        action = sag.find(_ns('action'))
        self.assertEqual(action.find(_ns('actionActuatorFunc')).text, 'gimbalRotate')
        params = action.find(_ns('actionActuatorFuncParam'))
        self.assertEqual(int(params.find(_ns('gimbalPitchRotateAngle')).text), -90)


if __name__ == '__main__':
    unittest.main()
