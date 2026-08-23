#!/usr/bin/env python3

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import attention_audit as audit


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "questions.sample.json"
AS_OF = datetime(2026, 8, 23, 9, tzinfo=timezone.utc)


class AttentionAuditTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = audit.AuditStore(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def make_snapshot(self):
        return audit.snapshot(SOURCE, self.store, AS_OF, 14, "test-seed")

    def test_snapshot_fixes_denominators_without_exposure(self):
        receipt = self.make_snapshot()
        self.assertEqual(6, receipt["counts"]["structurally_eligible"])
        self.assertEqual(2, receipt["counts"]["active"])
        self.assertEqual(3, receipt["counts"]["unclaimed"])
        self.assertEqual([], self.store.exposures())

    def test_surface_records_availability_but_does_not_claim(self):
        receipt = self.make_snapshot()
        event, questions = audit.surface(
            SOURCE, self.store, receipt["audit_id"], 2, AS_OF
        )
        self.assertEqual(2, len(questions))
        self.assertFalse(event["claim_created"])
        self.assertTrue(all(not question["active"] for question in questions))
        self.assertEqual([], self.store.responses())

    def test_repeated_surface_reports_prior_exposure(self):
        receipt = self.make_snapshot()
        first, _ = audit.surface(SOURCE, self.store, receipt["audit_id"], 3, AS_OF)
        second, _ = audit.surface(SOURCE, self.store, receipt["audit_id"], 3, AS_OF)
        self.assertEqual(set(first["question_ids"]), set(second["question_ids"]))
        self.assertTrue(all(count == 1 for count in second["prior_exposures"].values()))

    def test_claim_requires_exposure_and_changes_next_projection(self):
        receipt = self.make_snapshot()
        with self.assertRaises(ValueError):
            audit.respond(
                self.store,
                receipt["audit_id"],
                "claimed",
                AS_OF,
                "Q-001",
                "worth a fresh joint window",
            )
        event, _ = audit.surface(SOURCE, self.store, receipt["audit_id"], 3, AS_OF)
        target = event["question_ids"][0]
        audit.respond(
            self.store,
            receipt["audit_id"],
            "claimed",
            AS_OF,
            target,
            "this session elects to carry it",
        )
        later = audit.snapshot(
            SOURCE,
            self.store,
            datetime(2026, 8, 24, 9, tzinfo=timezone.utc),
            14,
            "test-seed",
        )
        self.assertIn(target, later["active_ids"])
        self.assertNotIn(target, later["unclaimed_ids"])

    def test_no_change_is_audit_level_not_question_disposition(self):
        receipt = self.make_snapshot()
        audit.surface(SOURCE, self.store, receipt["audit_id"], 2, AS_OF)
        audit.respond(
            self.store, receipt["audit_id"], "no-change", AS_OF
        )
        later = audit.snapshot(SOURCE, self.store, AS_OF, 14, "test-seed")
        self.assertEqual(receipt["unclaimed_ids"], later["unclaimed_ids"])

    def test_surface_refuses_a_changed_frontier(self):
        receipt = self.make_snapshot()
        changed = Path(self.temp.name) / "changed.json"
        document = json.loads(SOURCE.read_text())
        document["questions"][0]["title"] = "A rewritten question"
        changed.write_text(json.dumps(document))
        with self.assertRaises(ValueError):
            audit.surface(changed, self.store, receipt["audit_id"], 1, AS_OF)


if __name__ == "__main__":
    unittest.main()
