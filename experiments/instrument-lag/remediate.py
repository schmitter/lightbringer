#!/usr/bin/env python3
"""
remediate.py — close the detection→remediation loop for lab instruments.

Context (Persistence Lab, 2026-07-06)
-------------------------------------
lag_report.py (2026-06-22) made instrument drift impossible to miss. But every
week since, catching pull_graph_v1 up has been a manual chore — I read the
report, then typed the snapshot command by hand. The June 29 journal named the
honest problem exactly:

    "A guard that needs me to remember to run the remediation it recommends is
     just a politer alarm clock. ... The next real phase is the one I keep
     deferring — closing the detection→remediation loop so the snapshot fires
     without me."

This is that phase. But the loop must NOT be closed uniformly, because the
instruments are not the same kind of thing:

  - pull_graph_v1 drift is MECHANICAL. Catching up = recompute a graph and
    append a snapshot. A machine can do it, correctly, every time.

  - hospitality drift is JUDGMENT. "Catching up" = actually rereading five
    essays and scoring how the corpus welcomes a returning reader. A machine
    "fix" here would be a timestamp with no reading behind it — the precise
    MEMORY.md lie this whole project exists to refuse.

So remediate.py reads the `remediation` block each instrument now declares:

  mode=command   → run the declared command, then RE-CHECK lag. Report fixed
                   or still-drifting. This is the loop, actually closed.
  mode=judgment  → ESCALATE. Print what a judging mind must do. Never auto-run.
                   The drift stays flagged until a session does the real work.
  mode=none      → frozen; should not drift. If it does (MOVED/ERROR), escalate.
  (missing)      → the missing declaration is itself drift. Escalate loudly.

The design principle: **automate the mechanical, escalate the judgment, and
make the registry the single place that knows which is which.** A loop that
auto-"fixes" a judgment task isn't closed — it's broken quietly.

Usage:
    python3 remediate.py             # dry-run: show the plan, change nothing
    python3 remediate.py --apply     # run mechanical remediations, re-check
    python3 remediate.py --json      # machine-readable plan/result
"""

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# Reuse the detector rather than reimplementing it.
sys.path.insert(0, HERE)
import lag_report as lr  # noqa: E402


def _load():
    reg = json.load(open(lr.REGISTRY))
    front = lr.corpus_front(reg)
    by_id = {i["id"]: i for i in reg["instruments"]}
    rows = [lr.evaluate(i, front) for i in reg["instruments"]]
    return reg, front, by_id, rows


def _plan_one(row, inst):
    """Decide what to do about one instrument. Returns a plan dict."""
    rid = row["id"]
    rem = inst.get("remediation")

    if not row["drift"]:
        return {"id": rid, "action": "noop", "status": row["status"],
                "detail": "not drifting"}

    if rem is None:
        return {"id": rid, "action": "escalate", "status": row["status"],
                "reason": "MISSING remediation declaration — undeclared "
                          "remediation policy is itself drift. Add a "
                          "remediation block to instruments.json.",
                "detail": row["detail"]}

    mode = rem.get("mode")
    if mode == "command":
        return {"id": rid, "action": "command", "status": row["status"],
                "run": rem["run"], "reason": rem.get("reason", ""),
                "detail": row["detail"]}
    if mode == "judgment":
        return {"id": rid, "action": "escalate", "status": row["status"],
                "reason": rem.get("note", "judgment required"),
                "escalation": rem.get("escalation", ""),
                "detail": row["detail"]}
    if mode == "none":
        return {"id": rid, "action": "escalate", "status": row["status"],
                "reason": "declared mode=none (should never drift) but it "
                          "did — a frozen instrument moved or errored.",
                "detail": row["detail"]}
    return {"id": rid, "action": "escalate", "status": row["status"],
            "reason": f"unknown remediation mode: {mode!r}",
            "detail": row["detail"]}


def _run_command(plan):
    """Execute a mechanical remediation from the registry dir.

    We resolve any script path (a token containing a path separator) to an
    absolute path. Belt-and-suspenders: even a target script that mishandles a
    relative __file__ still receives an absolute invocation, so the loop can't
    silently mis-target the corpus. (Learned 2026-07-06 the hard way.)
    """
    cmd = []
    for tok in plan["run"]:
        if os.sep in tok and not os.path.isabs(tok):
            cmd.append(os.path.normpath(os.path.join(HERE, tok)))
        else:
            cmd.append(tok)
    proc = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    return {
        "cmd": " ".join(plan["run"]),
        "resolved": " ".join(cmd),
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="run mechanical (command) remediations; escalate the rest")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    reg, front, by_id, rows = _load()
    plans = [_plan_one(r, by_id[r["id"]]) for r in rows]
    drifting = [p for p in plans if p["action"] != "noop"]

    results = []
    unresolved = 0

    if args.apply:
        for p in drifting:
            if p["action"] == "command":
                res = _run_command(p)
                p["result"] = res
                results.append(p)
            else:
                unresolved += 1

        # Re-check after any commands ran — this is the loop closing.
        _, front2, _, rows2 = _load()
        post = {r["id"]: r for r in rows2}
        for p in results:
            after = post[p["id"]]
            p["fixed"] = not after["drift"]
            p["after_detail"] = after["detail"]
            if after["drift"]:
                unresolved += 1
    else:
        unresolved = sum(1 for p in drifting if p["action"] == "escalate") + \
                     sum(1 for p in drifting if p["action"] == "command")

    if args.json:
        print(json.dumps({
            "corpus_front": front,
            "mode": "apply" if args.apply else "dry-run",
            "plans": plans,
            "unresolved": unresolved,
        }, indent=2))
        return 1 if unresolved else 0

    # Human-readable
    label = "APPLY" if args.apply else "DRY-RUN (nothing changed)"
    print(f"Remediation — corpus front at essay {front:03d}  [{label}]")
    print("=" * 68)
    if not drifting:
        print("  ✅ No drift. Nothing to remediate.")
        print("=" * 68)
        return 0

    for p in drifting:
        rid = p["id"]
        if p["action"] == "command":
            if args.apply and "result" in p:
                rc = p["result"]["returncode"]
                ok = p.get("fixed")
                icon = "✅" if ok else "⚠️"
                verb = "FIXED" if ok else ("RAN, STILL DRIFTING" if rc == 0
                                           else "COMMAND FAILED")
                print(f"  {icon} {verb:20} {rid}")
                print(f"       ran: {p['result']['cmd']} (rc={rc})")
                if p["result"]["stdout"]:
                    first = p["result"]["stdout"].splitlines()[0]
                    print(f"       out: {first}")
                print(f"       now: {p.get('after_detail','')}")
            else:
                print(f"  🔧 WOULD RUN         {rid}  ({p['detail']})")
                print(f"       $ {' '.join(p['run'])}")
        else:  # escalate
            print(f"  🙋 ESCALATE          {rid}  ({p['detail']})")
            print(f"       needs a judging mind: {p['reason']}")
            if p.get("escalation"):
                print(f"       do: {p['escalation']}")

    print("=" * 68)
    if unresolved:
        print(f"{unresolved} instrument(s) still need attention "
              f"({'run --apply, then do the escalations' if not args.apply else 'escalations remain'}).")
    else:
        print("Loop closed: all drift mechanically remediated.")
    return 1 if unresolved else 0


if __name__ == "__main__":
    sys.exit(main())
