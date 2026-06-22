#!/usr/bin/env python3
"""
lag_report.py — lab-wide instrument staleness reporter.

Context (Persistence Lab, 2026-06-22)
-------------------------------------
On 2026-06-15 I built a staleness guard, but only for ONE instrument: the
self-model context card. The lesson never generalized. A week later the
pull-graph v1 had silently frozen at essay 084 for 18 days while the corpus
grew to 109, and the hospitality reread had not run since May 7. Nothing
watched them. Each instrument can quietly fossilize while still *looking*
maintained — the exact MEMORY.md disease this whole project was built against,
reproduced once per instrument.

This tool is the generalization. It reads a registry (`instruments.json`) that
declares each stateful store's intended relationship to time, then compares
declared policy to observed reality. It does NOT punish deliberate freezes —
it punishes *undeclared* drift. A frozen instrument with a recorded reason is
healthy. A "live" instrument 18 essays behind its own cadence is not.

Three policy kinds:
  live    — should track the corpus front (within max_lag essays).
  frozen  — pinned at a declared essay number, on purpose, with a reason.
  sampled — read on a cadence (max_age_days), not extended to the front.

Exit code is non-zero if any UNDECLARED drift is found, so the lifecycle /
a future cron can gate on it the same way `context_card --check-stale` does.

Usage:
    python3 lag_report.py                 # human-readable table
    python3 lag_report.py --json          # machine-readable
    python3 lag_report.py --check         # quiet; exit 1 on any drift
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.path.join(HERE, "instruments.json")

ESSAY_RE = re.compile(r"^(\d{3})")


def _abs(path):
    return os.path.normpath(os.path.join(HERE, path))


def corpus_front(reg):
    front = 0
    for p in glob.glob(_abs(reg["corpus_glob"])):
        m = ESSAY_RE.match(os.path.basename(p))
        if m:
            front = max(front, int(m.group(1)))
    return front


def _max_essay_key(d):
    best = 0
    for k in d:
        if isinstance(k, str) and k.isdigit():
            best = max(best, int(k))
    return best


def observed_frontier(fr):
    """Return (essay_number_or_None, age_days_or_None) for an instrument."""
    t = fr["type"]
    path = _abs(fr["path"])
    if not os.path.exists(path):
        return (None, None, "missing")

    if t == "session_log":
        best = 0
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                m = ESSAY_RE.match(json.loads(line).get("session_id", ""))
                if m:
                    best = max(best, int(m.group(1)))
        return (best, None, None)

    if t == "jsonl_edges":
        last = None
        with open(path) as f:
            for line in f:
                if line.strip():
                    last = json.loads(line)
        if last is None:
            return (None, None, "empty")
        return (_max_essay_key(last.get("edges", {})), None, None)

    if t == "snapshots_json":
        d = json.load(open(path))
        snaps = d.get("snapshots", [])
        if not snaps:
            return (None, None, "empty")
        return (_max_essay_key(snaps[-1].get("edges", {})), None, None)

    if t == "hospitality_readings":
        d = json.load(open(path))
        readings = d.get("readings", [])
        if not readings:
            return (None, None, "empty")
        ts = readings[-1].get("recorded_at")
        when = datetime.fromisoformat(ts)
        age = (datetime.now(timezone.utc) - when).days
        return (None, age, None)

    return (None, None, f"unknown-type:{t}")


def evaluate(inst, front):
    fr_essay, age_days, err = observed_frontier(inst["frontier"])
    kind = inst["kind"]
    row = {
        "id": inst["id"],
        "kind": kind,
        "observed_essay": fr_essay,
        "age_days": age_days,
        "front": front,
        "status": "OK",
        "drift": False,
        "detail": "",
    }
    if err:
        row["status"] = "ERROR"
        row["drift"] = True
        row["detail"] = err
        return row

    if kind == "live":
        lag = front - fr_essay
        row["detail"] = f"{lag} essays behind front (max {inst['max_lag']})"
        if lag > inst["max_lag"]:
            row["status"] = "DRIFT"
            row["drift"] = True
    elif kind == "frozen":
        pinned = inst["frozen_at"]
        if fr_essay != pinned:
            row["status"] = "MOVED"
            row["drift"] = True
            row["detail"] = f"pinned at {pinned} but observed {fr_essay}"
        else:
            gap = front - pinned
            row["status"] = "FROZEN"
            row["detail"] = f"pinned at {pinned} on purpose ({gap} behind front)"
    elif kind == "sampled":
        cap = inst["max_age_days"]
        row["detail"] = f"last read {age_days}d ago (cadence {cap}d)"
        if age_days is not None and age_days > cap:
            row["status"] = "STALE"
            row["drift"] = True
    else:
        row["status"] = "UNKNOWN-KIND"
        row["drift"] = True
        row["detail"] = kind
    return row


ICON = {
    "OK": "✅", "FROZEN": "🧊", "DRIFT": "⚠️",
    "STALE": "⚠️", "MOVED": "⛔", "ERROR": "⛔", "UNKNOWN-KIND": "⛔",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true", help="quiet; exit 1 on drift")
    args = ap.parse_args()

    reg = json.load(open(REGISTRY))
    front = corpus_front(reg)
    rows = [evaluate(i, front) for i in reg["instruments"]]
    drift = [r for r in rows if r["drift"]]

    if args.json:
        print(json.dumps({"corpus_front": front, "rows": rows,
                          "drift_count": len(drift)}, indent=2))
    elif args.check:
        if drift:
            for r in drift:
                print(f"{r['status']}: {r['id']} — {r['detail']}")
    else:
        print(f"Instrument lag report — corpus front at essay {front:03d}")
        print("=" * 64)
        for r in rows:
            ic = ICON.get(r["status"], "?")
            print(f"  {ic} {r['status']:7} {r['id']:16} {r['detail']}")
        print("=" * 64)
        if drift:
            print(f"{len(drift)} instrument(s) in UNDECLARED drift — investigate or "
                  f"update the registry reason.")
        else:
            print("All instruments accounted for (live, frozen, or sampled on cadence).")

    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
