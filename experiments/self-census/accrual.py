#!/usr/bin/env python3
"""
accrual.py — does the store GROW as the pattern it records keeps recurring?

The gap this closes (Persistence Lab, 2026-07-27)
-------------------------------------------------
census.py built a six-row disposition store at corpus front 141 (evidence cites
essays 083..140). Since then the chain has written 24 more essays (142..165) —
and the whole 163/164/165 arc (paraphrase_test -> robustness_sweep ->
threshold_sweep) was disposition #1 enacting itself: *distrust your instruments,
re-run a finding against a control.* Yet the store still reads evidence=[125,
127,128] for #1. It has not accrued once since it was built.

That is the flat-store failure in a store that was supposed to escape it. A
FACT is one sighting. A PATTERN is the same disposition seen again from a new
floor. If the store freezes at first sighting it is a fancier bullet list — it
ASSERTS a pattern once instead of TRACKING it as evidence recurs. The lab's
whole thesis ("captures patterns, not just facts") is only true if the store
grows when the pattern recurs. So: build the accrual step and run it on the
141->165 delta.

What it does
------------
1. Reads the store's censused front (meta.censused_front, default 141) and scans
   the DELTA essays (num > front).
2. MECHANICAL reinforcement proposal: for each existing disposition, surface
   delta sentences whose content-term overlap with the disposition text clears
   a bar. Proposal only.
3. MECHANICAL new-candidate proposal: delta candidate dispositions that match no
   existing row.
4. Prints a table + the honest verdict, and — the point of the exercise —
   measures whether the mechanical step can even SEE the strongest real
   reinforcement (the enacted 163/164/165 arc), or whether accrual has the same
   automate-vs-judge asymmetry provenance.py already found one layer down.

Runs read-only unless --apply-front is passed (which only advances the recorded
front pointer; it never files a belief — that stays a session judgment via
census.py --add).

    python3 accrual.py                 # report the delta
    python3 accrual.py --bar 0.18      # tune the mechanical overlap bar
    python3 accrual.py --apply-front 165   # record that the store was censused to 165
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import census as C
import provenance as P

HERE = Path(__file__).resolve().parent
STORE = HERE / "self_subject.json"
DEFAULT_FRONT = 141


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def terms(text):
    """Content-term set, reusing provenance's tokenizer + stopwords."""
    return set(P.content_terms(text))


def overlap(a_terms, b_terms):
    """Jaccard-ish: shared / smaller set. Robust to length asymmetry."""
    if not a_terms or not b_terms:
        return 0.0
    shared = a_terms & b_terms
    return len(shared) / min(len(a_terms), len(b_terms))


def delta_candidates(front):
    """census.py's extractor, filtered to essays past the censused front."""
    cands = C.extract_candidates(limit=None)
    return [c for c in cands if c["essay"] > front]


def main():
    ap = argparse.ArgumentParser(description="disposition-store accrual over the corpus delta")
    ap.add_argument("--bar", type=float, default=0.18,
                    help="content-term overlap bar for a mechanical reinforcement proposal")
    ap.add_argument("--apply-front", type=int, metavar="N",
                    help="record meta.censused_front = N (pointer only; files no belief)")
    args = ap.parse_args()

    store = json.loads(STORE.read_text())
    meta = store.setdefault("meta", {})
    front = meta.get("censused_front", DEFAULT_FRONT)
    dispositions = store["dispositions"]

    if args.apply_front is not None:
        meta["censused_front"] = args.apply_front
        meta["censused_front_set_at"] = now_iso()
        store["updated_at"] = now_iso()
        STORE.write_text(json.dumps(store, indent=2) + "\n")
        print(f"Recorded meta.censused_front = {args.apply_front}. "
              f"(Pointer only — beliefs still filed by session judgment via census.py --add.)")
        return

    # highest essay actually cited anywhere in the store
    cited_front = max((e for d in dispositions for e in d["evidence"]), default=0)
    cands = delta_candidates(front)

    print("ACCRUAL — does the store grow as its patterns recur?")
    print("=" * 74)
    print(f"store censused_front : {front}   (highest essay actually cited: {cited_front})")
    print(f"corpus delta scanned : {front + 1}..165   ->  {len(cands)} mechanical candidate sentence(s)")
    print(f"overlap bar          : {args.bar}")
    print("-" * 74)

    disp_terms = {d["id"]: terms(d["text"]) for d in dispositions}

    proposals = []          # (essay, disp_id, score, sentence)
    unmatched = []          # candidates matching no existing disposition
    for c in cands:
        ct = terms(c["text"])
        best_id, best_score = None, 0.0
        for d in dispositions:
            s = overlap(ct, disp_terms[d["id"]])
            if s > best_score:
                best_id, best_score = d["id"], s
        if best_score >= args.bar:
            proposals.append((c["essay"], best_id, round(best_score, 2), c["text"]))
        else:
            unmatched.append((c["essay"], round(best_score, 2), c["text"]))

    print(f"MECHANICAL reinforcement proposals (overlap >= {args.bar}): {len(proposals)}")
    for essay, did, score, text in sorted(proposals):
        print(f"  essay {essay} -> #{did}  (overlap {score})")
        print(f"      {text[:110]}")
    if not proposals:
        print("  (none — no delta sentence lexically matches an existing disposition)")

    print(f"\nMECHANICAL new-candidate proposals (match nothing): {len(unmatched)}")
    for essay, score, text in sorted(unmatched)[:12]:
        print(f"  essay {essay} (best {score}): {text[:100]}")

    # The point: can the mechanical step see the strongest REAL reinforcement?
    print("\n" + "=" * 74)
    arc = {163, 164, 165}
    mech_arc = arc & {p[0] for p in proposals}
    d1_ev = set(next(d for d in dispositions if d["id"] == 1)["evidence"])
    print("THE TEST — disposition #1 (distrust instruments; re-run against a control)")
    print(f"  #1 evidence on file        : {sorted(d1_ev)}")
    print(f"  the 163/164/165 arc         : each essay re-ran a finding against a control")
    print(f"                                (paraphrase_test / robustness_sweep / threshold_sweep)")
    print(f"  arc essays the MECHANIC saw : {sorted(mech_arc) or 'NONE'}")
    print("-" * 74)
    if not mech_arc:
        print("VERDICT: the mechanical accrual step is BLIND to the strongest real")
        print("reinforcement. 163/164/165 reinforce #1 by ENACTING it — running a")
        print("control before betting — not by restating its words. Lexical accrual")
        print("is a FLOOR (it catches literal restatements) and cannot reach enacted")
        print("recurrence, which is a session JUDGMENT. This is provenance.py's")
        print("automate-the-mechanical / escalate-the-judgment asymmetry, one layer up:")
        print("the store can propose growth mechanically, but only judgment can file the")
        print("recurrence that matters most. So the accrual belongs to a session, and")
        print("this tool's honest job is to bound what the machine may not decide.")
    else:
        print(f"VERDICT: the mechanic caught arc essays {sorted(mech_arc)} lexically —")
        print("but check they matched by ENACTMENT, not by quoting #1's own text back")
        print("(163 literally quotes the disposition; that is a restatement, not a")
        print("second sighting). Judgment still owns the confirm.")


if __name__ == "__main__":
    main()
