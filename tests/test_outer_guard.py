import unittest
import os
import json
import csv
from pathlib import Path
from core.outer_guard import tile_airspace, parse_flight_log, identify_cowans, Cowan

class TestOuterGuard(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("data/tests/outer_guard")
        self.test_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.test_dir / "test_flight_log.csv"
        self.output_dir = self.test_dir / "output"
        
        # Create a mock flight log with a clear hazard (power line pole)
        # Power line height = 10m. Flight altitude = 60m. 
        # Ultrasonic height should be 50m when over the pole.
        with open(self.log_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['latitude', 'longitude', 'altitude', 'ultrasonic_height'])
            # 10 points of clear air
            for i in range(10):
                writer.writerow([36.0 + i*0.0001, -76.0, 60.0, 60.0])
            # 3 points of "power line" (pole hits)
            # Consistent height and spacing (pole pattern detection requires 3+)
            writer.writerow([36.0010, -76.0, 60.0, 50.0]) # hit
            writer.writerow([36.0011, -76.0, 60.0, 60.0]) # gap
            writer.writerow([36.0015, -76.0, 60.0, 50.0]) # hit
            writer.writerow([36.0016, -76.0, 60.0, 60.0]) # gap
            writer.writerow([36.0020, -76.0, 60.0, 50.0]) # hit

    def test_parse_flight_log(self):
        readings = parse_flight_log(str(self.log_path))
        self.assertEqual(len(readings), 15)
        self.assertEqual(readings[10]['rangefinder_m'], 50.0)

    def test_identify_cowans(self):
        readings = parse_flight_log(str(self.log_path))
        cowans = identify_cowans(readings, [])
        
        # Should identify at least the 3 pole hits
        self.assertTrue(len(cowans) >= 1)
        self.assertTrue(any(c.height_m >= 10.0 for c in cowans))
        
    def test_tile_airspace(self):
        cowans = tile_airspace(str(self.log_path), str(self.output_dir))
        self.assertTrue(len(cowans) >= 1)

        # Check if output file exists
        out_file = self.output_dir / "test_flight_log_tiled_airspace.json"
        self.assertTrue(out_file.exists())

        with open(out_file) as f:
            data = json.load(f)
            self.assertFalse(data['rangefinder_missing'])
            self.assertEqual(len(data['cowans']), len(cowans))

    def test_parse_flight_log_flags_missing_rangefinder(self):
        """A log without any rangefinder column must be marked degraded."""
        bad_log = self.test_dir / "no_rangefinder.csv"
        with open(bad_log, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['latitude', 'longitude', 'altitude'])
            writer.writerow([36.0, -76.0, 60.0])
        readings, meta = parse_flight_log(str(bad_log), with_meta=True)
        self.assertTrue(meta['rangefinder_missing'])
        self.assertEqual(len(readings), 1)
        # Degraded fallback: range = alt, so hazard height is zero
        self.assertEqual(readings[0]['rangefinder_m'], readings[0]['drone_alt_m'])

        # And the flag must surface in the tile_airspace output file
        out_dir = self.output_dir / "degraded"
        tile_airspace(str(bad_log), str(out_dir))
        with open(out_dir / "no_rangefinder_tiled_airspace.json") as f:
            data = json.load(f)
        self.assertTrue(data['rangefinder_missing'])

    def test_parse_flight_log_with_meta_ok_when_rangefinder_present(self):
        readings, meta = parse_flight_log(str(self.log_path), with_meta=True)
        self.assertFalse(meta['rangefinder_missing'])
        self.assertEqual(len(readings), 15)

if __name__ == '__main__':
    unittest.main()
