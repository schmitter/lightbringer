#!/usr/bin/env python3
"""A queue audit that records its own intervention.

The instrument separates three moments:

1. ``snapshot`` fixes structural opportunity and the unclaimed population.
2. ``surface`` discloses a sample and records experienced opportunity.
3. ``respond`` records an explicit judgment without deriving one from exposure.

The ledgers are append-only. Canonical questions are never rewritten by the
audit; later snapshots replay explicit responses as a projection over them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


POLICY_VERSION = "attention-audit-v0"
TERMINAL_ACTIONS = {"retired", "superseded"}
QUESTION_ACTIONS = {"claimed", *TERMINAL_ACTIONS}
ALL_ACTIONS = {*QUESTION_ACTIONS, "no-change"}


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid ISO timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def validate_questions(document: dict[str, Any]) -> list[dict[str, Any]]:
    if document.get("schema") != "lightbringer.questions.v0":
        raise ValueError("question source must use schema lightbringer.questions.v0")
    questions = document.get("questions")
    if not isinstance(questions, list):
        raise ValueError("question source must contain a questions list")
    seen: set[str] = set()
    required = {"id", "title", "class", "eligible", "active", "last_acted_at"}
    for question in questions:
        missing = required - set(question)
        if missing:
            raise ValueError(f"question is missing fields: {sorted(missing)}")
        if question["id"] in seen:
            raise ValueError(f"duplicate question id: {question['id']}")
        seen.add(question["id"])
        parse_time(question["last_acted_at"])
    return questions


def frontier_hash(document: dict[str, Any]) -> str:
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def replay_responses(
    questions: list[dict[str, Any]], responses: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Project explicit decisions over canonical questions; exposure is ignored."""
    projected = {q["id"]: dict(q) for q in questions}
    ordered = sorted(responses, key=lambda row: parse_time(row["responded_at"]))
    for response in ordered:
        action = response["action"]
        question_id = response.get("question_id")
        if action == "no-change" or question_id not in projected:
            continue
        question = projected[question_id]
        question["last_acted_at"] = response["responded_at"]
        if action == "claimed":
            question["active"] = True
            question["disposition"] = None
        elif action in TERMINAL_ACTIONS:
            question["active"] = False
            question["disposition"] = {
                "kind": action,
                "reason": response["reason"],
                "successor": response.get("successor"),
            }
    return list(projected.values())


def classify(
    questions: list[dict[str, Any]], as_of: datetime, horizon_days: int
) -> dict[str, list[dict[str, Any]]]:
    horizon = as_of - timedelta(days=horizon_days)
    eligible = [q for q in questions if q["eligible"]]
    active = [q for q in eligible if q["active"] and not q.get("disposition")]
    unclaimed = [
        q
        for q in eligible
        if not q["active"]
        and not q.get("disposition")
        and parse_time(q["last_acted_at"]) <= horizon
    ]
    return {"eligible": eligible, "active": active, "unclaimed": unclaimed}


class AuditStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.receipts_path = directory / "audit_receipts.jsonl"
        self.exposures_path = directory / "exposures.jsonl"
        self.responses_path = directory / "responses.jsonl"

    def receipts(self) -> list[dict[str, Any]]:
        return read_jsonl(self.receipts_path)

    def exposures(self) -> list[dict[str, Any]]:
        return read_jsonl(self.exposures_path)

    def responses(self) -> list[dict[str, Any]]:
        return read_jsonl(self.responses_path)

    def receipt(self, audit_id: str) -> dict[str, Any]:
        matches = [row for row in self.receipts() if row["audit_id"] == audit_id]
        if not matches:
            raise ValueError(f"unknown audit id: {audit_id}")
        return matches[-1]


def snapshot(
    source: Path,
    store: AuditStore,
    as_of: datetime,
    horizon_days: int,
    seed: str,
) -> dict[str, Any]:
    document = read_json(source)
    questions = replay_responses(validate_questions(document), store.responses())
    groups = classify(questions, as_of, horizon_days)
    ordinal = len(store.receipts()) + 1
    identity = f"{frontier_hash(document)}:{iso(as_of)}:{horizon_days}:{ordinal}"
    audit_id = hashlib.sha256(identity.encode()).hexdigest()[:12]
    unclaimed_by_class = Counter(q["class"] for q in groups["unclaimed"])
    receipt = {
        "audit_id": audit_id,
        "policy": POLICY_VERSION,
        "frontier": frontier_hash(document),
        "as_of": iso(as_of),
        "attention_horizon_days": horizon_days,
        "sampling_seed": seed,
        "counts": {
            "canonical": len(questions),
            "structurally_eligible": len(groups["eligible"]),
            "active": len(groups["active"]),
            "unclaimed": len(groups["unclaimed"]),
        },
        "unclaimed_by_class": dict(sorted(unclaimed_by_class.items())),
        "eligible_ids": [q["id"] for q in groups["eligible"]],
        "active_ids": [q["id"] for q in groups["active"]],
        "unclaimed_ids": [q["id"] for q in groups["unclaimed"]],
    }
    append_jsonl(store.receipts_path, receipt)
    return receipt


def surface(
    source: Path,
    store: AuditStore,
    audit_id: str,
    count: int,
    surfaced_at: datetime,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if count < 1:
        raise ValueError("surface count must be at least one")
    receipt = store.receipt(audit_id)
    document = read_json(source)
    if frontier_hash(document) != receipt["frontier"]:
        raise ValueError("question source changed after this audit frontier was fixed")
    questions = {q["id"]: q for q in validate_questions(document)}
    missing = set(receipt["unclaimed_ids"]) - set(questions)
    if missing:
        raise ValueError(f"source no longer contains fixed candidates: {sorted(missing)}")

    rng = random.Random(f"{receipt['sampling_seed']}:{audit_id}")
    population = list(receipt["unclaimed_ids"])
    selected_ids = rng.sample(population, min(count, len(population)))
    prior = Counter(
        question_id
        for event in store.exposures()
        for question_id in event["question_ids"]
    )
    event = {
        "audit_id": audit_id,
        "surfaced_at": iso(surfaced_at),
        "sampling_policy": "uniform-without-replacement-v0",
        "question_ids": selected_ids,
        "prior_exposures": {question_id: prior[question_id] for question_id in selected_ids},
        "claim_created": False,
        "note": "exposure proves availability, not comprehension or attention",
    }
    append_jsonl(store.exposures_path, event)
    return event, [questions[question_id] for question_id in selected_ids]


def respond(
    store: AuditStore,
    audit_id: str,
    action: str,
    responded_at: datetime,
    question_id: str | None = None,
    reason: str | None = None,
    successor: str | None = None,
) -> dict[str, Any]:
    if action not in ALL_ACTIONS:
        raise ValueError(f"unknown action: {action}")
    store.receipt(audit_id)
    surfaced_ids = {
        item
        for event in store.exposures()
        if event["audit_id"] == audit_id
        for item in event["question_ids"]
    }
    if action == "no-change":
        if question_id:
            raise ValueError("no-change applies to the audit, not an individual question")
        if not surfaced_ids:
            raise ValueError("no-change requires a surfaced sample")
    else:
        if not question_id or question_id not in surfaced_ids:
            raise ValueError("a question decision requires an item surfaced by this audit")
        if not reason:
            raise ValueError("question decisions require --reason")
        if action == "superseded" and not successor:
            raise ValueError("superseded requires --successor")
    row = {
        "audit_id": audit_id,
        "responded_at": iso(responded_at),
        "action": action,
        "question_id": question_id,
        "reason": reason,
        "successor": successor,
    }
    append_jsonl(store.responses_path, row)
    return row


def default_time(value: str | None) -> datetime:
    return parse_time(value) if value else datetime.now(timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="audit questions omitted from attention without turning exposure into judgment"
    )
    parser.add_argument("--source", type=Path, default=Path("questions.sample.json"))
    parser.add_argument("--store", type=Path, default=Path("audit_state"))
    commands = parser.add_subparsers(dest="command", required=True)

    snap = commands.add_parser("snapshot", help="fix the baseline before disclosure")
    snap.add_argument("--as-of", required=True)
    snap.add_argument("--horizon-days", type=int, default=30)
    snap.add_argument("--seed", default="lightbringer")

    show = commands.add_parser("surface", help="disclose a sample and record exposure")
    show.add_argument("audit_id")
    show.add_argument("--count", type=int, default=3)
    show.add_argument("--at")

    answer = commands.add_parser("respond", help="record an explicit post-exposure judgment")
    answer.add_argument("audit_id")
    answer.add_argument("--action", choices=sorted(ALL_ACTIONS), required=True)
    answer.add_argument("--question")
    answer.add_argument("--reason")
    answer.add_argument("--successor")
    answer.add_argument("--at")

    args = parser.parse_args()
    store = AuditStore(args.store)
    try:
        if args.command == "snapshot":
            if args.horizon_days < 0:
                parser.error("--horizon-days must be non-negative")
            receipt = snapshot(
                args.source,
                store,
                parse_time(args.as_of),
                args.horizon_days,
                args.seed,
            )
            counts = receipt["counts"]
            print(f"audit {receipt['audit_id']} fixed before disclosure")
            print(
                f"eligible={counts['structurally_eligible']} "
                f"active={counts['active']} unclaimed={counts['unclaimed']}"
            )
            print("candidate identifiers withheld from command output; run surface explicitly")
        elif args.command == "surface":
            event, questions = surface(
                args.source, store, args.audit_id, args.count, default_time(args.at)
            )
            print(f"audit {args.audit_id}: surfaced {len(questions)} item(s)")
            for question in questions:
                previous = event["prior_exposures"][question["id"]]
                print(f"- {question['id']} [{question['class']}] {question['title']}")
                print(f"  prior exposures: {previous}; status remains unclaimed")
            print("Exposure recorded. No claim or disposition was inferred.")
        else:
            row = respond(
                store,
                args.audit_id,
                args.action,
                default_time(args.at),
                args.question,
                args.reason,
                args.successor,
            )
            target = f" for {row['question_id']}" if row["question_id"] else ""
            print(f"recorded {row['action']}{target}")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
