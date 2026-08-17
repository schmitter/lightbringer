#!/usr/bin/env python3

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hospitality


def reading(day):
    return {"recorded_at": f"2026-04-{day:02d}T09:00:00+00:00"}


def session(day):
    return {"timestamp": f"2026-04-{day:02d}T08:00:00+00:00"}


class OverlayCoverageTest(unittest.TestCase):
    def test_minimum_count_is_only_first_gate(self):
        data = {"readings": [reading(1), reading(2), reading(3)]}
        result = hospitality.overlay_coverage(data, {"focused": [1, 2]},
                                               [session(1), session(2)])
        self.assertEqual("insufficient_hospitality", result["status"])

    def test_disjoint_windows_block_comparison(self):
        data = {"readings": [reading(20), reading(21), reading(22), reading(23)]}
        drift = {"focused": [0.1, 0.2, 0.3]}
        result = hospitality.overlay_coverage(
            data, drift, [session(10), session(11), session(12)]
        )
        self.assertEqual("disjoint_windows", result["status"])
        self.assertEqual(4, result["post_drift_readings"])

    def test_vector_and_timestamp_rows_must_align(self):
        data = {"readings": [reading(1), reading(2), reading(3), reading(4)]}
        result = hospitality.overlay_coverage(
            data, {"focused": [1, 2, 3]}, [session(1), session(2)]
        )
        self.assertEqual("unaligned_statistical_channel", result["status"])

    def test_overlapping_windows_are_ready(self):
        data = {"readings": [reading(2), reading(3), reading(4), reading(5)]}
        result = hospitality.overlay_coverage(
            data,
            {"focused": [1, 2, 3, 4, 5, 6]},
            [session(1), session(2), session(3), session(4), session(5), session(6)],
        )
        self.assertEqual("ready", result["status"])


if __name__ == "__main__":
    unittest.main()
