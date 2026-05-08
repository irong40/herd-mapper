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
            self.assertEqual(len(data), len(cowans))

if __name__ == '__main__':
    unittest.main()
