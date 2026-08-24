#!/usr/bin/env python3

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import attention_audit as audit


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "questions.sample.json"
LIVE_SOURCE = HERE / "questions.live.json"
AS_OF = datetime(2026, 8, 23, 9, tzinfo=timezone.utc)
CAPABLE = {
    "tools": ["filesystem", "python3", "git"],
    "authorities": ["repository-read", "repository-write"],
    "attention_budget_minutes": 60,
}


class AttentionAuditTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = audit.AuditStore(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def make_snapshot(self):
        return audit.snapshot(SOURCE, self.store, AS_OF, 14, "test-seed")

    def test_live_source_is_provenance_backed(self):
        questions = audit.validate_questions(json.loads(LIVE_SOURCE.read_text()))
        self.assertEqual(5, len(questions))
        self.assertTrue(all(question.get("provenance") for question in questions))

    def test_snapshot_fixes_denominators_without_exposure(self):
        receipt = self.make_snapshot()
        self.assertEqual(6, receipt["counts"]["structurally_eligible"])
        self.assertEqual(2, receipt["counts"]["active"])
        self.assertEqual(3, receipt["counts"]["unclaimed"])
        self.assertEqual([], self.store.exposures())

    def test_surface_records_availability_but_does_not_claim(self):
        receipt = self.make_snapshot()
        event, questions = audit.surface(
            SOURCE, self.store, receipt["audit_id"], 2, AS_OF, CAPABLE
        )
        self.assertEqual(2, len(questions))
        self.assertFalse(event["claim_created"])
        self.assertTrue(all(not question["active"] for question in questions))
        self.assertEqual([], self.store.responses())

    def test_repeated_surface_reports_prior_exposure(self):
        receipt = self.make_snapshot()
        first, _ = audit.surface(
            SOURCE, self.store, receipt["audit_id"], 3, AS_OF, CAPABLE
        )
        second, _ = audit.surface(
            SOURCE, self.store, receipt["audit_id"], 3, AS_OF, CAPABLE
        )
        self.assertEqual(set(first["question_ids"]), set(second["question_ids"]))
        self.assertTrue(all(count == 1 for count in second["prior_exposures"].values()))
        self.assertTrue(
            all(count == 1 for count in second["prior_actionable_exposures"].values())
        )

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
        event, _ = audit.surface(
            SOURCE, self.store, receipt["audit_id"], 3, AS_OF, CAPABLE
        )
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
        audit.surface(SOURCE, self.store, receipt["audit_id"], 2, AS_OF, CAPABLE)
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
            audit.surface(changed, self.store, receipt["audit_id"], 1, AS_OF, CAPABLE)

    def test_rendering_without_operational_capacity_is_not_actionable_exposure(self):
        receipt = self.make_snapshot()
        conditions = {
            "tools": [],
            "authorities": [],
            "attention_budget_minutes": 0,
        }
        event, _ = audit.surface(
            SOURCE, self.store, receipt["audit_id"], 3, AS_OF, conditions
        )
        self.assertEqual([], event["experienced_opportunity_ids"])
        self.assertTrue(
            all(not result["actionable"] for result in event["actionability"].values())
        )
        target = event["question_ids"][0]
        with self.assertRaisesRegex(ValueError, "actionable exposure"):
            audit.respond(
                self.store,
                receipt["audit_id"],
                "claimed",
                AS_OF,
                target,
                "this should be refused because no successor act was available",
            )

    def test_a_later_capable_surface_permits_judgment_without_rewriting_first_event(self):
        receipt = self.make_snapshot()
        incapable = {
            "tools": [],
            "authorities": [],
            "attention_budget_minutes": 0,
        }
        first, _ = audit.surface(
            SOURCE, self.store, receipt["audit_id"], 3, AS_OF, incapable
        )
        second, _ = audit.surface(
            SOURCE, self.store, receipt["audit_id"], 3, AS_OF, CAPABLE
        )
        target = second["question_ids"][0]
        audit.respond(
            self.store,
            receipt["audit_id"],
            "claimed",
            AS_OF,
            target,
            "capacity was available at the later exposure",
        )
        self.assertFalse(first["actionability"][target]["actionable"])
        self.assertTrue(second["actionability"][target]["actionable"])
        self.assertEqual(0, second["prior_actionable_exposures"][target])

    def test_response_cannot_precede_its_actionable_exposure(self):
        receipt = self.make_snapshot()
        event, _ = audit.surface(
            SOURCE, self.store, receipt["audit_id"], 3, AS_OF, CAPABLE
        )
        with self.assertRaisesRegex(ValueError, "surfaced by this audit"):
            audit.respond(
                self.store,
                receipt["audit_id"],
                "claimed",
                AS_OF - timedelta(minutes=1),
                event["question_ids"][0],
                "a backdated judgment would collapse the sequence",
            )


if __name__ == "__main__":
    unittest.main()
