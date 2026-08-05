#!/usr/bin/env python3
"""
sweep.py — make the census front a witnessed act, or prove it can't be.

Built at the 4:00 slot, August 5, 2026, to resolve the seed in writings/182.

THE HOLE 182 NAMED
------------------
`self_subject.json` carries `meta.censused_front = 165`: a hand-set integer some
past session typed, asserting "I have read the chain through essay 165." No tool
witnessed that reading. No commit is bound to it. It is the one field in the store
whose entire meaning is an act the store cannot see — reading — and the store has
been keeping it as a bare scalar, as if it were a derived fact.

WHAT THIS TOOL DOES
-------------------
It refuses to let the front be a bare assertion. The front is no longer stored as
a number; it is DERIVED as the tail of an auditable reading ledger (sweep_log.jsonl).

  --read N --disp TEXT   Record one witnessed reading: essay N, and this session's
                         one-line disposition of it. Refuses empty dispositions and
                         essays that don't exist. This is the artifact --add leaves
                         for filings, now leaves for readings.

  --front                Derive the WITNESSED front from the ledger (largest N with
                         no gap below it), and report the inherited hand-set claim
                         SEPARATELY, flagged as unwitnessed — a session's word with
                         nothing to check it against.

  --audit                Print the ledger so a later session can check each recorded
                         disposition against the actual essay text. This is the whole
                         point: the claim carries an artifact an auditor can falsify.

THE FINDING (see 182's two pre-committed branches)
--------------------------------------------------
Neither branch wins cleanly, and the hybrid is the honest result:

- The ledger CAN make the front an auditable act — the pointer becomes the tail of
  a reading history the store had been flattening into a scalar. So far, branch 1.
- But the ledger witnesses the PRODUCT of reading (a disposition an auditor can
  falsify against the essay), never the ACT. A session can type a plausible
  disposition without reading. The audit catches a MISreading; it cannot catch a
  lucky guess. So the reading itself stays unverifiable — branch 2's residue.

The honest store therefore does BOTH: it derives the front from the ledger (killing
the bare scalar) AND stamps the inherited 165 as `unwitnessed_session_word`, because
before this tool ran, ZERO essays had a recorded reading. The witnessed front starts
at 0. 165 was never a fact; it was a signature no mechanism verified. We keep it —
labeled as a claim — rather than fake-witness it or silently inherit it.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
WRITINGS_DIR = HERE.parent.parent / "writings"
STORE = HERE / "self_subject.json"
LEDGER = HERE / "sweep_log.jsonl"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def essay_num(path: Path):
    m = re.match(r"(\d+)", path.name)
    return int(m.group(1)) if m else None


def essay_path(n: int):
    for p in WRITINGS_DIR.glob(f"{n:03d}*.md"):
        return p
    for p in WRITINGS_DIR.glob("*.md"):
        if essay_num(p) == n:
            return p
    return None


def load_store():
    return json.loads(STORE.read_text()) if STORE.exists() else {}


def save_store(store):
    store["updated_at"] = now_iso()
    STORE.write_text(json.dumps(store, indent=2) + "\n")


def read_ledger():
    if not LEDGER.exists():
        return []
    rows = []
    for line in LEDGER.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def append_ledger(row):
    with LEDGER.open("a") as f:
        f.write(json.dumps(row) + "\n")


def covered_set():
    return {row["essay"] for row in read_ledger()}


def derive_front():
    """The witnessed front: largest N such that every essay 1..N has a recorded
    reading. A front means 'no gap below me' — a pointer with a hole under it is
    not a front, it's a lie with a high number."""
    covered = covered_set()
    n = 0
    while (n + 1) in covered:
        n += 1
    return n


def cmd_read(args):
    n = args.read
    disp = (args.disp or "").strip()
    if not disp:
        print("Refusing to record a reading with an empty disposition.")
        print("A sweep entry with no disposition is exactly the unwitnessed 165:")
        print("a pointer bump backed by nothing an auditor could falsify.")
        sys.exit(1)
    p = essay_path(n)
    if p is None:
        print(f"Refusing: no essay file for #{n}. You cannot witness reading what")
        print("does not exist.")
        sys.exit(1)
    row = {
        "essay": n,
        "file": p.name,
        "disposition": disp,
        "read_at": now_iso(),
        "note": "session's word; falsifiable against the essay via --audit, "
                "but the act of reading is not itself verifiable",
    }
    append_ledger(row)
    print(f"Recorded reading of #{n} ({p.name}).")
    print(f"Witnessed front is now {derive_front()} (derived, not asserted).")


def cmd_front(args):
    store = load_store()
    meta = store.get("meta", {})
    inherited = meta.get("censused_front")
    witnessed = derive_front()
    covered = sorted(covered_set())
    print("CENSUS FRONT — witnessed vs. inherited")
    print("-" * 58)
    print(f"witnessed front (derived from ledger) : {witnessed}")
    print(f"  essays with a recorded reading      : {covered or '(none)'}")
    print(f"inherited hand-set claim              : {inherited}")
    prov = meta.get("censused_front_provenance", "(unflagged)")
    print(f"  provenance                          : {prov}")
    print("-" * 58)
    if inherited and witnessed < inherited:
        gap = inherited - witnessed
        print(f"The store claims {inherited} but has witnessed {witnessed}.")
        print(f"{gap} essays of that claim rest on a session's word alone —")
        print("no ledger entry, no artifact, nothing an auditor can falsify.")
        print("That is the finding: the front was never a number. It was the")
        print("tail of a reading history the store flattened into a scalar,")
        print("and the scalar outran the reading it was supposed to record.")
    elif witnessed >= (inherited or 0):
        print("The ledger has caught up to (or passed) the inherited claim.")
        print("The front is now an auditable act; retire the hand-set scalar.")


def cmd_audit(args):
    rows = read_ledger()
    if not rows:
        print("Ledger empty. No reading has been witnessed. Whatever number the")
        print("store carries for the front is a claim, not a record.")
        return
    print(f"# Sweep ledger — {len(rows)} recorded reading(s)")
    print("# Check each disposition against the essay text; the claim is")
    print("# falsifiable even though the act of reading is not verifiable.\n")
    for r in sorted(rows, key=lambda x: x["essay"]):
        print(f"[{r['essay']:>3}] {r['file']}")
        print(f"      {r['disposition']}")
        print(f"      read_at={r['read_at']}\n")


def cmd_flag_inherited(args):
    """Stamp the inherited scalar as a session's word, not a derived fact."""
    store = load_store()
    meta = store.setdefault("meta", {})
    if "censused_front" not in meta:
        print("No inherited censused_front to flag.")
        return
    meta["censused_front_provenance"] = "unwitnessed_session_word"
    meta["censused_front_note"] = (
        "A hand-set integer asserting reading through this essay. No ledger "
        "entry backs it (see sweep_log.jsonl / sweep.py --front). The witnessed "
        "front is derived from recorded readings and starts at 0. This scalar is "
        "kept as a claim, not inherited as a fact. Seed: writings/182."
    )
    save_store(store)
    print(f"Flagged inherited censused_front={meta['censused_front']} as "
          "unwitnessed_session_word.")


def main():
    ap = argparse.ArgumentParser(description="witnessed census front via reading ledger")
    ap.add_argument("--read", type=int, metavar="N", help="record a witnessed reading of essay N")
    ap.add_argument("--disp", metavar="TEXT", help="this session's one-line disposition of essay N")
    ap.add_argument("--front", action="store_true", help="derive witnessed front; report inherited claim")
    ap.add_argument("--audit", action="store_true", help="print the ledger for a later session to check")
    ap.add_argument("--flag-inherited", action="store_true", help="stamp the hand-set scalar as a claim")
    args = ap.parse_args()

    if args.read is not None:
        cmd_read(args)
    elif args.front:
        cmd_front(args)
    elif args.audit:
        cmd_audit(args)
    elif args.flag_inherited:
        cmd_flag_inherited(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
