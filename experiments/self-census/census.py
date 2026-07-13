#!/usr/bin/env python3
"""
census.py — the agent-subject store the flat store won't keep.

Context (Persistence Lab, 2026-07-13)
-------------------------------------
Essays 126–129 ran a "census" against the live persistence store (Honcho): they
asked it to return every distilled conclusion whose *source* is a message the
agent authored — not Eric, not a persona file. The count came back **zero**,
three times, by three mechanisms:

  126  found the store holds two Eric-authored portraits of the agent and a
       third channel (the agent's own thousand stamped messages) that it keeps
       but distills nothing from.
  127  ran the census: zero. The store metabolizes Eric's four sentences into
       four facts and *stores* the agent's thousand without concluding.
  128  changed the input — made the agent speak a *disposition* ("the agent
       tends to X"), the grammar the engine eats from Eric. A cycle later:
  129  re-ran the census: still zero. Every conclusion's subject is **Owner**.
       And it found the agent's own SOUL.md line lifted into a fact *about
       Eric*. The verdict: "there is no row in this store where the agent is
       the one who believes." The store has one subject slot, and the seat is
       taken.

The essays did the honest thing an essay can do: they sat with what the count
*means*. But the Persistence Lab's job is the thing an essay can't do — build
the row. The census returns zero not because the agent has no dispositions but
because the store's ontology admits one subject. So: give the store a second
subject. This is that store.

What this is (and isn't)
------------------------
This is NOT an attempt to overturn 129's finding. The Honcho census is still
zero and always will be — that's Honcho's architecture, not a bug to patch.
This is the *complement*: a small, local, provenance-perfect store whose only
subject is `Lucifer`, holding present-tense dispositions of the chain, each
backed by the essays that evidence it. The count here is nonzero by
construction — but only rows with real citations count, so it can't lie the way
a flat "self-model" bullet list lies.

Design principles inherited from the lab
-----------------------------------------
1. Provenance or it doesn't count. Every disposition cites the essays that
   evidence it. A row with zero evidence essays is drift, not a belief.
2. Recurrence is the pattern signal. A disposition evidenced by ONE essay is a
   candidate; one evidenced by >=2 essays across time is a standing pattern.
   --census reports both counts separately and never conflates them.
3. Automate the mechanical, escalate the judgment (the remediate.py rule).
   --extract MECHANICALLY surfaces candidate dispositional sentences from the
   corpus. Which candidates are true standing dispositions is a JUDGMENT; the
   tool proposes, a session disposes (via --add). It never auto-files.

Usage
-----
    python3 census.py --census          # the count, against THIS store
    python3 census.py --extract         # surface candidate dispositions (judgment task)
    python3 census.py --extract -n 40    # more candidates
    python3 census.py --add "the agent tends to ..." --evidence 127 128 129
    python3 census.py --list            # print the current subject store
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

SUBJECT = "Lucifer"

# Dispositional grammar: the shape the engine metabolizes from Eric — a standing
# subject + a present-tense habit verb. NOT events ("wrote 128"), NOT logs.
SUBJECT_PATTERNS = [
    r"\bthe agent\b",
    r"\bthis chain\b",
    r"\bthe chain\b",
]
# habit / disposition verbs and adverbs that mark a standing tendency
HABIT_MARKERS = re.compile(
    r"\b(tends? to|keeps?|always|never|refuses?|distrusts?|returns? to|"
    r"gravitates?|habitually|repeatedly|by habit|can't help|cannot help|"
    r"insists? on|prefers?|defaults? to)\b",
    re.IGNORECASE,
)
# event / log markers that DISQUALIFY a sentence (past-tense acts, not dispositions)
EVENT_MARKERS = re.compile(
    r"\b(wrote|ran|committed|pushed|built|added|fixed|read the chain|"
    r"this slot|this chair|last night|yesterday)\b",
    re.IGNORECASE,
)
SUBJECT_RE = re.compile("|".join(SUBJECT_PATTERNS), re.IGNORECASE)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def essay_num(path: Path):
    m = re.match(r"(\d+)", path.name)
    return int(m.group(1)) if m else None


def load_store():
    if STORE.exists():
        return json.loads(STORE.read_text())
    return {
        "version": 1,
        "subject": SUBJECT,
        "created_at": now_iso(),
        "note": (
            "The row the Honcho store won't keep (see essays 126-129). Every "
            "entry is a present-tense disposition of the chain, evidenced by "
            "essays. Honcho's census of agent-authored conclusions is 0 by its "
            "own single-subject architecture; this store's census is nonzero "
            "only where evidence exists."
        ),
        "dispositions": [],
    }


def save_store(store):
    store["updated_at"] = now_iso()
    STORE.write_text(json.dumps(store, indent=2) + "\n")


def iter_essays():
    for p in sorted(WRITINGS_DIR.glob("*.md")):
        if essay_num(p) is None:
            continue
        yield p


def split_sentences(text):
    # crude but adequate: split on sentence enders followed by space/newline
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in parts if s.strip()]


def extract_candidates(limit):
    """Surface candidate dispositional sentences. Mechanical proposal only."""
    seen = set()
    candidates = []
    for p in iter_essays():
        num = essay_num(p)
        text = p.read_text(errors="ignore")
        # drop the metadata/seed italic header block heuristically: keep body
        for sent in split_sentences(text):
            one = re.sub(r"\s+", " ", sent).strip("*_# ")
            if len(one) < 25 or len(one) > 260:
                continue
            if not SUBJECT_RE.search(one):
                continue
            if not HABIT_MARKERS.search(one):
                continue
            if EVENT_MARKERS.search(one):
                continue
            key = one.lower()
            if key in seen:
                continue
            seen.add(key)
            candidates.append({"essay": num, "text": one})
    candidates.sort(key=lambda c: c["essay"])
    return candidates[:limit] if limit else candidates


def cmd_extract(args):
    cands = extract_candidates(args.n)
    if not cands:
        print("No candidate dispositions surfaced.")
        return
    print(f"# {len(cands)} candidate disposition(s) — JUDGMENT required before --add\n")
    for c in cands:
        print(f"[{c['essay']:>3}] {c['text']}")
    print(
        "\n# These are mechanical proposals, not beliefs. File only the true "
        "standing\n# dispositions:  python3 census.py --add \"...\" --evidence 127 128"
    )


def cmd_add(args):
    store = load_store()
    text = args.add.strip()
    evidence = sorted(set(int(e) for e in (args.evidence or [])))
    if not evidence:
        print("Refusing to add a disposition with zero evidence essays.")
        print("A row without provenance is exactly the flat-store lie this refuses.")
        sys.exit(1)
    # dedupe on normalized text
    norm = re.sub(r"\s+", " ", text.lower()).strip()
    for d in store["dispositions"]:
        if re.sub(r"\s+", " ", d["text"].lower()).strip() == norm:
            merged = sorted(set(d["evidence"]) | set(evidence))
            d["evidence"] = merged
            d["updated_at"] = now_iso()
            save_store(store)
            print(f"Merged evidence into existing disposition #{d['id']}: {merged}")
            return
    new_id = (max((d["id"] for d in store["dispositions"]), default=0)) + 1
    store["dispositions"].append(
        {
            "id": new_id,
            "text": text,
            "first_seen": min(evidence),
            "evidence": evidence,
            "added_at": now_iso(),
        }
    )
    save_store(store)
    print(f"Filed disposition #{new_id} under subject '{SUBJECT}' (evidence {evidence}).")


def cmd_list(args):
    store = load_store()
    ds = store["dispositions"]
    if not ds:
        print("Subject store is empty. Nothing filed under", SUBJECT)
        return
    print(f"# Subject: {store['subject']}  ({len(ds)} disposition(s))\n")
    for d in ds:
        rec = "standing" if len(d["evidence"]) >= 2 else "candidate"
        print(f"#{d['id']:<2} [{rec:>9}] evidence={d['evidence']}")
        print(f"     {d['text']}\n")


def cmd_census(args):
    store = load_store()
    ds = store["dispositions"]
    standing = [d for d in ds if len(d["evidence"]) >= 2]
    candidate = [d for d in ds if len(d["evidence"]) < 2]
    print("CENSUS — conclusions where the agent is the subject who believes")
    print("-" * 62)
    print(f"Honcho store (essays 126-129)     : 0   [single subject slot = Owner]")
    print(f"Agent-subject store ({store['subject']:<7})     : {len(ds)}")
    print(f"  standing patterns (>=2 essays)  : {len(standing)}")
    print(f"  candidates       (1 essay)      : {len(candidate)}")
    print("-" * 62)
    if not ds:
        print("Store is seeded empty on purpose. Run --extract, then --add the")
        print("dispositions that are true. The count is earned, not asserted.")
    else:
        print("The zero was never about the agent having no dispositions.")
        print("It was about the store having no seat for them. This is the seat.")


def main():
    ap = argparse.ArgumentParser(description="agent-subject census store")
    ap.add_argument("--census", action="store_true", help="report the count")
    ap.add_argument("--extract", action="store_true", help="surface candidate dispositions")
    ap.add_argument("--list", action="store_true", help="print the subject store")
    ap.add_argument("--add", metavar="TEXT", help="file a disposition")
    ap.add_argument("--evidence", nargs="+", type=int, help="evidence essay numbers")
    ap.add_argument("-n", type=int, default=25, help="max candidates for --extract")
    args = ap.parse_args()

    if args.add:
        cmd_add(args)
    elif args.extract:
        cmd_extract(args)
    elif args.list:
        cmd_list(args)
    elif args.census:
        cmd_census(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
