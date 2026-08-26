"""
Visual-inference provenance contract.

A missing obstacle model must never be indistinguishable from "the model ran
and found nothing" — a silently absent visual layer lowers the computed Pass 2
safe altitude, which is a flight-safety condition. These tests pin the
safe-by-default semantics and prove the flag reaches every written artifact.

Ported from the fence-mapper Phase 3 stub-provenance pattern
(core/fence_condition_detector.py + core/deliverables.py STUB_BANNER_TEXT).
"""

import csv
import json
import unittest
from pathlib import Path

from core.visual_detector import (
    VISUAL_MODE_ONNX,
    VISUAL_MODE_STUB,
    VISUAL_STUB_BANNER_TEXT,
    detect_from_folder_with_provenance,
    resolve_visual_mode,
    visual_is_degraded,
)
from core.outer_guard import tile_airspace
from core.pipeline_runner import _write_obstacles


class TestResolveVisualMode(unittest.TestCase):
    def test_none_model_path_is_stub(self):
        self.assertEqual(resolve_visual_mode(None), VISUAL_MODE_STUB)

    def test_missing_file_is_stub(self):
        self.assertEqual(
            resolve_visual_mode('models/definitely_not_here.onnx'), VISUAL_MODE_STUB
        )

    def test_real_file_is_onnx(self):
        tmp = Path('data/tests/provenance')
        tmp.mkdir(parents=True, exist_ok=True)
        f = tmp / 'fake_model.onnx'
        f.write_bytes(b'not a real model, but it is a real file')
        try:
            self.assertEqual(resolve_visual_mode(str(f)), VISUAL_MODE_ONNX)
        finally:
            f.unlink()


class TestVisualIsDegraded(unittest.TestCase):
    """Safe by default: only an explicit 'onnx' stamp clears the flag."""

    def test_none_record_is_degraded(self):
        self.assertTrue(visual_is_degraded(None))

    def test_empty_record_is_degraded(self):
        self.assertTrue(visual_is_degraded({}))

    def test_legacy_record_without_mode_is_degraded(self):
        # Predates the provenance contract — must not be assumed real.
        self.assertTrue(visual_is_degraded({'obstacles': [], 'cowan_count': 0}))

    def test_explicit_stub_is_degraded(self):
        self.assertTrue(visual_is_degraded({'visual_mode': VISUAL_MODE_STUB}))

    def test_explicit_onnx_is_not_degraded(self):
        self.assertFalse(visual_is_degraded({'visual_mode': VISUAL_MODE_ONNX}))

    def test_in_flight_mode_key_also_accepted(self):
        self.assertFalse(visual_is_degraded({'mode': VISUAL_MODE_ONNX}))


class TestBannerConstant(unittest.TestCase):
    """The banner is the operator-facing contract — pin its substance."""

    def test_banner_names_the_condition_and_the_consequence(self):
        text = VISUAL_STUB_BANNER_TEXT.upper()
        self.assertIn('DEGRADED', text)
        self.assertIn('DID NOT RUN', text)
        # Must name what is missing, not just that something is.
        for hazard in ('POWER LINES', 'GUY WIRES', 'TOWERS'):
            self.assertIn(hazard, text)
        # Must state the safety consequence, not only the fact.
        self.assertIn('SAFE-ALTITUDE', text)


class TestDetectFromFolderProvenance(unittest.TestCase):
    def test_no_model_returns_stub_mode_and_no_model_path(self):
        d = Path('data/tests/provenance/images')
        d.mkdir(parents=True, exist_ok=True)
        result = detect_from_folder_with_provenance(str(d), model_path=None)
        self.assertEqual(result['mode'], VISUAL_MODE_STUB)
        self.assertIsNone(result['model_path'])
        self.assertEqual(result['obstacles'], [])
        self.assertTrue(visual_is_degraded(result))


class TestWrittenArtifactsCarryTheFlag(unittest.TestCase):
    """The FAIL condition this fix closes: mock mode must reach the artifact."""

    def setUp(self):
        self.mission_dir = Path('data/tests/provenance/mission')
        self.mission_dir.mkdir(parents=True, exist_ok=True)

    def test_write_obstacles_stamps_degraded_when_stub(self):
        _write_obstacles(
            self.mission_dir, 'TESTMISSION', [], visual_mode=VISUAL_MODE_STUB
        )
        payload = json.loads((self.mission_dir / 'obstacles.json').read_text())
        self.assertEqual(payload['visual_mode'], VISUAL_MODE_STUB)
        self.assertTrue(payload['visual_degraded'])
        self.assertEqual(payload['obstacles'], [])

    def test_write_obstacles_clears_flag_when_onnx(self):
        _write_obstacles(
            self.mission_dir, 'TESTMISSION', [], visual_mode=VISUAL_MODE_ONNX
        )
        payload = json.loads((self.mission_dir / 'obstacles.json').read_text())
        self.assertFalse(payload['visual_degraded'])

    def test_write_obstacles_defaults_to_degraded(self):
        """An un-stamped caller must produce a degraded artifact, not a clean one."""
        _write_obstacles(self.mission_dir, 'TESTMISSION', [])
        payload = json.loads((self.mission_dir / 'obstacles.json').read_text())
        self.assertTrue(payload['visual_degraded'])

    def test_tile_airspace_stamps_the_security_map(self):
        d = Path('data/tests/provenance/guard')
        d.mkdir(parents=True, exist_ok=True)
        log = d / 'PROVTEST.csv'
        with open(log, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['latitude', 'longitude', 'altitude', 'ultrasonic_height'])
            for i in range(10):
                w.writerow([36.0 + i * 0.0001, -76.0, 60.0, 60.0])

        tile_airspace(log_path=str(log), output_dir=str(d))  # default = stub
        out = json.loads((d / 'PROVTEST_tiled_airspace.json').read_text())
        self.assertEqual(out['visual_mode'], VISUAL_MODE_STUB)
        self.assertTrue(out['visual_degraded'])

        tile_airspace(log_path=str(log), output_dir=str(d),
                      visual_mode=VISUAL_MODE_ONNX)
        out = json.loads((d / 'PROVTEST_tiled_airspace.json').read_text())
        self.assertFalse(out['visual_degraded'])


if __name__ == '__main__':
    unittest.main()
