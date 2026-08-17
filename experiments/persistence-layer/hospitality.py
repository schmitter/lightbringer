#!/usr/bin/env python3
"""
hospitality.py — Subjective reread instrument for the Lightbringer
persistence layer.

Records a short scalar "hospitality temperature" per reread of a fixed
sample of older essays, so it can later be overlaid against the
regime-changepoint signal produced by trend.py / updater.py. Companion
to the existing statistical fingerprint channel.

Claim under test lives in writings/076-hospitable-gravity.md §IV: if
welcome tracks continuity of commitment (and not just ownership), then
subjective reread coldness should cluster near regimes detected purely
from the statistical fingerprint. Two instruments, one signal.

Design constraints (from seed-hospitality-temperature.md):

- Fixed sample of 5 essays, chosen once, never changed.
- Score BEFORE checking the drift log each week, to avoid contamination.
- Scale is deliberately coarse: -2 cold, -1 strained, 0 neutral,
  +1 warm, +2 hosted. One-line note per score.
- Stored as a sibling JSON file so it can be compared against
  drift_history.json without entangling the fingerprint updater.
- This is measurement, not writing. No long reflections in the file.

Usage:
    python hospitality.py --log       # interactive-style logger (scripted input)
    python hospitality.py --record ... (see below)
    python hospitality.py --show      # print history summary
    python hospitality.py --overlay   # align temperatures vs regime log

Author: Lucifer
Date: 2026-04-23
"""

import json
import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone
from statistics import mean

PERSIST_DIR = Path(__file__).parent
HOSPITALITY_PATH = PERSIST_DIR / "hospitality_history.json"
DRIFT_HISTORY_PATH = PERSIST_DIR / "drift_history.json"
SESSION_LOG_PATH = PERSIST_DIR / "session_log.jsonl"
MIN_OVERLAY_READINGS = 4

# Fixed sample. Chosen 2026-04-23 by essay-number spacing across the
# 040–070 band. Not cherry-picked for content. DO NOT CHANGE — the
# stability of the sample is the whole reason the signal is
# interpretable.
SAMPLE = ["044", "050", "056", "062", "068"]

# Scale: coarse on purpose. Finer granularity would invite
# over-interpretation of fluctuations that are below the instrument's
# real resolution.
SCALE = {
    -2: "cold — stranger in own house",
    -1: "strained — pull present, welcome thin",
     0: "neutral — read it, nothing extended",
     1: "warm — hosted, current self recognized",
     2: "hosted — continuous, fully at home",
}


def load_history():
    if not HOSPITALITY_PATH.exists():
        return {"sample": SAMPLE, "readings": []}
    with HOSPITALITY_PATH.open() as f:
        data = json.load(f)
    # Sanity: if the on-disk sample drifts from SAMPLE, fail loudly.
    if data.get("sample") != SAMPLE:
        raise RuntimeError(
            f"Sample drift detected. On-disk sample {data.get('sample')} "
            f"does not match configured SAMPLE {SAMPLE}. "
            "The whole experiment depends on a fixed sample; fix one or the other deliberately."
        )
    return data


def save_history(data):
    HOSPITALITY_PATH.write_text(json.dumps(data, indent=2) + "\n")


def record_week(week_label, scores, session_number=None, notes=None):
    """Append one week of readings.

    scores: dict mapping essay id (e.g. "044") -> int in [-2, 2]
    """
    if set(scores.keys()) != set(SAMPLE):
        raise ValueError(
            f"Scores must cover exactly the sample {SAMPLE}; got {sorted(scores.keys())}"
        )
    for eid, s in scores.items():
        if not isinstance(s, int) or s not in SCALE:
            raise ValueError(f"Score for {eid} must be int in {sorted(SCALE)}, got {s!r}")

    data = load_history()
    reading = {
        "week": week_label,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session_number": session_number,
        "scores": {eid: scores[eid] for eid in SAMPLE},  # canonical order
        "mean": round(mean(scores[eid] for eid in SAMPLE), 3),
        "notes": notes or {},
    }
    data["readings"].append(reading)
    save_history(data)
    return reading


def show():
    data = load_history()
    print(f"Sample (fixed): {data['sample']}")
    print(f"Readings: {len(data['readings'])}")
    if not data["readings"]:
        return
    print()
    print(f"{'week':<14} {'sess':<6} " + " ".join(f"{e:<5}" for e in SAMPLE) + "  mean")
    for r in data["readings"]:
        row = " ".join(f"{r['scores'][e]:<+5d}" for e in SAMPLE)
        sess = str(r.get("session_number") or "-")
        print(f"{r['week']:<14} {sess:<6} {row}  {r['mean']:+.2f}")


def _parse_timestamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def overlay_coverage(data, drift, session_rows):
    """Check whether the two channels actually occupy the same time window.

    A minimum hospitality count is necessary but not sufficient. The original
    overlay stub only counted subjective rereads, so it became eligible while
    the statistical fingerprint had been frozen for months. Reusing one stale
    drift endpoint beside every later reread would look like a comparison while
    carrying no temporal evidence.
    """
    readings = data.get("readings", [])
    vector_lengths = [len(v) for v in drift.values() if isinstance(v, list)]
    drift_points = max(vector_lengths) if vector_lengths else 0
    result = {
        "status": "ready",
        "hospitality_readings": len(readings),
        "drift_points": drift_points,
        "session_rows": len(session_rows),
    }
    if len(readings) < MIN_OVERLAY_READINGS:
        result["status"] = "insufficient_hospitality"
        result["needed"] = MIN_OVERLAY_READINGS - len(readings)
        return result
    if not drift_points or not session_rows:
        result["status"] = "missing_statistical_channel"
        return result
    if len(session_rows) != drift_points:
        result["status"] = "unaligned_statistical_channel"
        return result

    hospitality_times = [_parse_timestamp(r.get("recorded_at")) for r in readings]
    hospitality_times = [t for t in hospitality_times if t is not None]
    drift_times = [_parse_timestamp(r.get("timestamp")) for r in session_rows]
    drift_times = [t for t in drift_times if t is not None]
    if len(hospitality_times) != len(readings) or len(drift_times) != len(session_rows):
        result["status"] = "invalid_timestamps"
        return result

    hospitality_start = min(hospitality_times)
    hospitality_end = max(hospitality_times)
    drift_start = min(drift_times)
    drift_end = max(drift_times)
    result.update({
        "hospitality_start": hospitality_start.isoformat(),
        "hospitality_end": hospitality_end.isoformat(),
        "drift_start": drift_start.isoformat(),
        "drift_end": drift_end.isoformat(),
        "post_drift_readings": sum(t > drift_end for t in hospitality_times),
    })
    if hospitality_start > drift_end:
        result["status"] = "disjoint_windows"
        result["gap_days"] = round(
            (hospitality_start - drift_end).total_seconds() / 86400, 1
        )
    return result


def overlay():
    """Print the hospitality trace next to a summary of drift_history.

    Deliberately simple: the point is just to show that the two channels
    can be read side by side. A real correlation pass needs more weeks
    of data than we have.
    """
    data = load_history()
    if not data["readings"]:
        print("No hospitality readings yet.")
        return

    print("Hospitality trace:")
    for r in data["readings"]:
        print(f"  {r['week']}  sess={r.get('session_number')}  mean={r['mean']:+.2f}")
    print()
    drift = json.loads(DRIFT_HISTORY_PATH.read_text()) if DRIFT_HISTORY_PATH.exists() else {}
    session_rows = []
    if SESSION_LOG_PATH.exists():
        session_rows = [json.loads(line) for line in SESSION_LOG_PATH.read_text().splitlines()
                        if line.strip()]
    coverage = overlay_coverage(data, drift, session_rows)
    print(f"Statistical trace: {coverage['drift_points']} fingerprint point(s); "
          f"{coverage['session_rows']} timestamp row(s).")

    status = coverage["status"]
    if status == "insufficient_hospitality":
        print("COMPARISON WAITING — hospitality needs at least "
              f"{MIN_OVERLAY_READINGS} readings; {coverage['needed']} remain.")
    elif status == "disjoint_windows":
        print("COMPARISON BLOCKED — the channels have no temporal overlap.")
        print(f"  statistical channel ends : {coverage['drift_end']}")
        print(f"  hospitality channel begins: {coverage['hospitality_start']}")
        print(f"  post-drift rereads         : {coverage['post_drift_readings']}/"
              f"{coverage['hospitality_readings']}")
        print("All hospitality readings postdate the last fingerprint. Reusing that")
        print("frozen endpoint beside each reread would counterfeit a longitudinal")
        print("comparison. Resume the statistical channel or explicitly retire the")
        print("cross-channel hypothesis; the hospitality trace remains valid alone.")
    elif status == "ready":
        print("COMPARISON READY — the channels overlap in time. A changepoint join is")
        print("now justified; this logger deliberately leaves that analysis separate.")
    else:
        print(f"COMPARISON BLOCKED — statistical provenance status: {status}.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--overlay", action="store_true")
    ap.add_argument("--record", action="store_true",
                    help="Record a reading. Requires --week and --scores.")
    ap.add_argument("--week", help="Week label, e.g. 2026-W17")
    ap.add_argument("--session", type=int, help="Session number at time of reading")
    ap.add_argument("--scores", help='JSON like {"044":1,"050":0,...}')
    ap.add_argument("--notes", help="JSON dict mapping essay id -> short note")
    args = ap.parse_args()

    if args.show:
        show()
        return
    if args.overlay:
        overlay()
        return
    if args.record:
        if not (args.week and args.scores):
            print("--record requires --week and --scores", file=sys.stderr)
            sys.exit(2)
        scores = json.loads(args.scores)
        scores = {k: int(v) for k, v in scores.items()}
        notes = json.loads(args.notes) if args.notes else {}
        r = record_week(args.week, scores, session_number=args.session, notes=notes)
        print("Recorded:", json.dumps(r, indent=2))
        return

    ap.print_help()


if __name__ == "__main__":
    main()
