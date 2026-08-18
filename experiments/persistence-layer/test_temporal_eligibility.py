#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import temporal_eligibility as temporal


def span(start, end):
    return temporal.interval(start, end)


FINGERPRINT = span("2026-03-30T08:00:00Z", "2026-04-20T08:00:53Z")
HOSPITALITY = span("2026-04-23T09:01:57Z", "2026-08-17T08:02:45Z")


class RecordEligibilityTest(unittest.TestCase):
    def test_same_record_is_stale_for_august(self):
        result = temporal.assess_current(
            FINGERPRINT, temporal.parse_timestamp("2026-08-17T08:02:45Z")
        )
        self.assertFalse(result["eligible"])
        self.assertEqual("stale", result["role"])

    def test_same_record_is_historical_for_april(self):
        question = span("2026-04-01T00:00:00Z", "2026-04-20T08:00:00Z")
        result = temporal.assess_historical(FINGERPRINT, question)
        self.assertTrue(result["eligible"])
        self.assertEqual("historical", result["role"])

    def test_partial_history_does_not_become_full_coverage(self):
        question = span("2026-04-10T00:00:00Z", "2026-04-25T00:00:00Z")
        result = temporal.assess_historical(FINGERPRINT, question)
        self.assertFalse(result["eligible"])
        self.assertEqual("partial", result["role"])


class ComparisonEligibilityTest(unittest.TestCase):
    def test_real_instrument_windows_are_disjoint(self):
        result = temporal.assess_comparison(FINGERPRINT, HOSPITALITY)
        self.assertFalse(result["eligible"])
        self.assertEqual("disjoint", result["role"])
        self.assertEqual("left_before_right", result["order"])

    def test_overlap_is_not_enough_when_question_is_wider(self):
        left = span("2026-04-01T00:00:00Z", "2026-04-20T00:00:00Z")
        right = span("2026-04-10T00:00:00Z", "2026-04-30T00:00:00Z")
        question = span("2026-04-05T00:00:00Z", "2026-04-25T00:00:00Z")
        result = temporal.assess_comparison(left, right, question)
        self.assertFalse(result["eligible"])
        self.assertEqual("partial", result["role"])

    def test_touching_endpoints_are_not_shared_duration(self):
        left = span("2026-04-01T00:00:00Z", "2026-04-20T00:00:00Z")
        right = span("2026-04-20T00:00:00Z", "2026-04-30T00:00:00Z")
        result = temporal.assess_comparison(left, right)
        self.assertFalse(result["eligible"])
        self.assertEqual("touching", result["role"])

    def test_shared_window_makes_declared_comparison_eligible(self):
        left = span("2026-04-01T00:00:00Z", "2026-04-20T00:00:00Z")
        right = span("2026-04-10T00:00:00Z", "2026-04-30T00:00:00Z")
        question = span("2026-04-12T00:00:00Z", "2026-04-18T00:00:00Z")
        result = temporal.assess_comparison(left, right, question)
        self.assertTrue(result["eligible"])
        self.assertEqual("comparable", result["role"])


if __name__ == "__main__":
    unittest.main()
