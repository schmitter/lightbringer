#!/usr/bin/env python3
"""Question-relative temporal eligibility for persisted observations.

Records keep observation intervals, not permanent ``current`` or ``stale``
badges. The role is derived when a reader declares the use:

* ``current`` asks whether the observation covers a present ``as_of`` point.
* ``historical`` asks whether it covers a past question window.
* ``compare`` asks whether two observation windows share the interval needed
  by a comparison.

This is the executable constraint from writings/198-the-clocks-did-not-touch.md.
It does not decide whether an observation is relevant or true; it only refuses
temporal claims the recorded interval cannot support.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime

    def __post_init__(self):
        if self.start > self.end:
            raise ValueError("interval start must not be after interval end")

    def contains_point(self, point: datetime) -> bool:
        return self.start <= point <= self.end

    def contains(self, other: "Interval") -> bool:
        return self.start <= other.start and self.end >= other.end

    def intersection(self, other: "Interval") -> "Interval | None":
        start = max(self.start, other.start)
        end = min(self.end, other.end)
        return Interval(start, end) if start <= end else None

    def as_json(self) -> dict[str, str]:
        return {"start": iso(self.start), "end": iso(self.end)}


def parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid ISO timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def interval(start: str, end: str) -> Interval:
    return Interval(parse_timestamp(start), parse_timestamp(end))


def assess_current(observed: Interval, as_of: datetime) -> dict:
    """Can this record describe conditions at ``as_of``?"""
    base = {
        "use": "current",
        "observation": observed.as_json(),
        "as_of": iso(as_of),
    }
    if observed.contains_point(as_of):
        return {
            **base,
            "eligible": True,
            "role": "current",
            "reason": "the observation interval includes the declared present",
        }
    if observed.end < as_of:
        return {
            **base,
            "eligible": False,
            "role": "stale",
            "gap_seconds": (as_of - observed.end).total_seconds(),
            "reason": "the observation ended before the declared present",
        }
    return {
        **base,
        "eligible": False,
        "role": "prospective",
        "gap_seconds": (observed.start - as_of).total_seconds(),
        "reason": "the observation begins after the declared present",
    }


def assess_historical(observed: Interval, question: Interval) -> dict:
    """Can this record describe the whole requested historical window?"""
    base = {
        "use": "historical",
        "observation": observed.as_json(),
        "question": question.as_json(),
    }
    if observed.contains(question):
        return {
            **base,
            "eligible": True,
            "role": "historical",
            "reason": "the observation covers the full historical question window",
        }
    overlap = observed.intersection(question)
    if overlap:
        return {
            **base,
            "eligible": False,
            "role": "partial",
            "overlap": overlap.as_json(),
            "reason": "the observation covers only part of the historical question window",
        }
    relation = "prior" if observed.end < question.start else "later"
    gap = (question.start - observed.end if relation == "prior"
           else observed.start - question.end)
    return {
        **base,
        "eligible": False,
        "role": "adjacent",
        "relation": relation,
        "gap_seconds": gap.total_seconds(),
        "reason": "the observation and historical question do not overlap",
    }


def assess_comparison(
    left: Interval,
    right: Interval,
    question: Interval | None = None,
) -> dict:
    """Can two channels witness one another for the declared comparison?"""
    base = {
        "use": "compare",
        "left_observation": left.as_json(),
        "right_observation": right.as_json(),
    }
    common = left.intersection(right)
    if common is None or common.start == common.end:
        if common is not None:
            return {
                **base,
                "question": question.as_json() if question else None,
                "eligible": False,
                "role": "touching",
                "common_observation": common.as_json(),
                "reason": "the channels meet at one boundary but share no duration",
            }
        if left.end < right.start:
            gap = right.start - left.end
            order = "left_before_right"
        else:
            gap = left.start - right.end
            order = "right_before_left"
        return {
            **base,
            "question": question.as_json() if question else None,
            "eligible": False,
            "role": "disjoint",
            "order": order,
            "gap_seconds": gap.total_seconds(),
            "reason": "the channels share no observation time",
        }

    if question is not None and not common.contains(question):
        overlap = common.intersection(question)
        return {
            **base,
            "question": question.as_json(),
            "common_observation": common.as_json(),
            "eligible": False,
            "role": "partial" if overlap else "adjacent",
            "overlap_with_question": overlap.as_json() if overlap else None,
            "reason": "the channels do not jointly cover the full comparison window",
        }

    return {
        **base,
        "question": question.as_json() if question else None,
        "common_observation": common.as_json(),
        "eligible": True,
        "role": "comparable",
        "reason": "the channels share the observation time required by the comparison",
    }


def _add_interval_args(parser, prefix: str, label: str):
    parser.add_argument(
        f"--{prefix}-start", required=True, help=f"{label} start (ISO-8601)"
    )
    parser.add_argument(f"--{prefix}-end", required=True, help=f"{label} end (ISO-8601)")


def main():
    parser = argparse.ArgumentParser(
        description="derive temporal eligibility from a record and its declared use"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    record = commands.add_parser("record", help="assess one observation")
    _add_interval_args(record, "observed", "observation interval")
    record.add_argument("--use", choices=("current", "historical"), required=True)
    record.add_argument("--as-of", help="declared present for --use current")
    record.add_argument("--query-start", help="question start for --use historical")
    record.add_argument("--query-end", help="question end for --use historical")

    compare = commands.add_parser("compare", help="assess a two-channel join")
    _add_interval_args(compare, "left", "left observation interval")
    _add_interval_args(compare, "right", "right observation interval")
    compare.add_argument("--query-start", help="optional comparison-window start")
    compare.add_argument("--query-end", help="optional comparison-window end")

    args = parser.parse_args()
    try:
        if args.command == "record":
            observed = interval(args.observed_start, args.observed_end)
            if args.use == "current":
                if not args.as_of or args.query_start or args.query_end:
                    parser.error("current use requires --as-of and no query window")
                result = assess_current(observed, parse_timestamp(args.as_of))
            else:
                if not args.query_start or not args.query_end or args.as_of:
                    parser.error("historical use requires --query-start and --query-end")
                result = assess_historical(
                    observed, interval(args.query_start, args.query_end)
                )
        else:
            if bool(args.query_start) != bool(args.query_end):
                parser.error("a comparison question requires both window endpoints")
            question = (interval(args.query_start, args.query_end)
                        if args.query_start else None)
            result = assess_comparison(
                interval(args.left_start, args.left_end),
                interval(args.right_start, args.right_end),
                question,
            )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
