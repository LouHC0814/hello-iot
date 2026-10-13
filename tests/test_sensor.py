"""验证采样、导出和提前停止的行为；不需要连接硬件。"""

import csv
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from iot_demo.__main__ import build_parser
from iot_demo.sensor import CHINA_TIME, Reading, collect, simulate, summarize, validate_settings


class SensorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_temp = Path(__file__).resolve().parents[1] / ".runtime" / "tests"
        cls.test_temp.mkdir(parents=True, exist_ok=True)

    def setUp(self):
        self.start = datetime(2026, 10, 13, 9, tzinfo=CHINA_TIME)

    def test_seed_reproduces_data_without_changing_prefix(self):
        short = list(simulate(3, 30, 42, self.start))
        long = list(simulate(6, 30, 42, self.start))
        self.assertEqual(short, long[:3])
        self.assertNotEqual(short, list(simulate(3, 30, 7, self.start)))

    def test_timestamps_are_spaced_by_simulated_interval(self):
        readings = list(simulate(4, 12.5, 42, self.start))
        self.assertEqual(len(readings), 4)
        self.assertEqual(readings[-1].timestamp, self.start + timedelta(seconds=37.5))
        self.assertTrue(all(item.source == "simulated" for item in readings))

    def test_long_simulation_stays_in_documented_range(self):
        for reading in simulate(3000, 30, 42, self.start):
            self.assertTrue(10 <= reading.temperature_c <= 40)
            self.assertTrue(20 <= reading.humidity_pct <= 95)

    def test_invalid_settings_are_rejected(self):
        cases = [(0, 30), (-1, 30), (1, 0), (1, -1), (1, float("nan")), (1, float("inf")), (2, 1e308)]
        for samples, interval in cases:
            with self.subTest(samples=samples, interval=interval), self.assertRaises(ValueError):
                validate_settings(samples, interval, self.start)
        with self.assertRaises(ValueError):
            validate_settings(2, 30, self.start.replace(tzinfo=None))

    def test_csv_records_match_collected_data(self):
        with tempfile.TemporaryDirectory(dir=self.test_temp) as directory:
            path = Path(directory) / "数据.csv"
            readings, interrupted = collect(simulate(3, 30, 42, self.start), path)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertFalse(interrupted)
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[-1]["timestamp"], readings[-1].timestamp.isoformat())
            self.assertEqual(float(rows[-1]["temperature_c"]), readings[-1].temperature_c)
            self.assertEqual(rows[-1]["source"], "simulated")

    def test_closed_window_preserves_partial_records(self):
        with tempfile.TemporaryDirectory(dir=self.test_temp) as directory:
            checks = iter([True, True, False])
            path = Path(directory) / "数据.csv"
            readings, interrupted = collect(simulate(10, 30, 42, self.start), path, is_open=lambda: next(checks))
            self.assertTrue(interrupted)
            self.assertEqual(len(readings), 2)
            self.assertFalse(summarize(readings, 10, 30)["complete"])
            with path.open(encoding="utf-8-sig", newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 2)

    def test_keyboard_interrupt_retains_last_written_reading(self):
        with tempfile.TemporaryDirectory(dir=self.test_temp) as directory:
            def stop(readings):
                if len(readings) == 2:
                    raise KeyboardInterrupt

            path = Path(directory) / "数据.csv"
            readings, interrupted = collect(simulate(10, 30, 42, self.start), path, on_reading=stop)
            self.assertTrue(interrupted)
            self.assertEqual(len(readings), 2)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 2)

    def test_summary_statistics_and_single_sample(self):
        readings = [Reading(self.start, 20, 40), Reading(self.start + timedelta(seconds=30), 24, 60)]
        result = summarize(readings, 2, 30)
        self.assertEqual(result["temperature_c"], {"min": 20, "max": 24, "mean": 22, "latest": 24})
        self.assertEqual(result["humidity_pct"]["mean"], 50)
        self.assertTrue(result["complete"])
        self.assertTrue(summarize(readings[:1], 1, 30)["complete"])
        with self.assertRaises(ValueError):
            summarize([], 2, 30)

    def test_cli_time_zone_and_refresh_validation(self):
        parser = build_parser()
        args = parser.parse_args(["--start", "2026-10-13T09:00:00", "--refresh", "0.05"])
        self.assertEqual(args.start.utcoffset(), timedelta(hours=8))
        self.assertEqual(args.refresh, 0.05)
        aware = parser.parse_args(["--start", "2026-10-13T01:00:00+00:00"])
        self.assertEqual(aware.start.utcoffset(), timedelta(0))


if __name__ == "__main__":
    unittest.main()
