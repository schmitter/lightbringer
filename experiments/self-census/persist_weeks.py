#!/usr/bin/env python3
"""
persist_weeks.py — make the store hold the week, so independence stops being a
git log in a trench coat.

Context (Persistence Lab, seed 175 → this build)
-------------------------------------------------
Essay 174 declared the schema out loud:

    "The persistence layer stores the write-week of every evidence write, and
     reads a disposition's independence as its distinct-week count."

But 175 checked how `citegraph.py --spread` actually gets the week and caught the
gap: it doesn't read the store at all. For every essay in every `evidence` list
it shells out to `git log --diff-filter=A --format=%cs`, resolves the filename by
glob, and only then computes the ISO week. The field 174 crowned was never IN
self_subject.json — it was recomputed from git history on every run. That is the
exact condition essay 168 diagnosed for the metric it killed: a field the essays
talk about that the store does not actually hold.

This build closes that gap. For each disposition's `evidence` entry it resolves
the essay's git add-week ONCE and writes an `evidence_weeks` map (essay -> ISO
week) onto the disposition. That map is what a store-only `--independence` reader
consumes, with zero git or filesystem calls.

The one discipline seed 175 pre-committed against
--------------------------------------------------
Do NOT also cache an `independence` integer per disposition. `write_week` is a
RAW timestamp (an essay's git add-date, which can't change) — not a verdict.
Independence stays a READ over those weeks, computed at query time, never stored
as its own field. The store persists the evidence, not the score. That is the
entire point of the 164→174 arc.

Usage
-----
    python3 persist_weeks.py            # write evidence_weeks into the store
    python3 persist_weeks.py --dry-run  # show what would be written, mutate nothing
"""

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

# Reuse the exact date/week resolution --spread uses, so the store-backed and
# git-backed views can only differ if the STORE is wrong — not if two code paths
# compute the week differently. Import the functions rather than re-implement.
from citegraph import essay_date, _isoweek, load_store, STORE


def resolve_weeks(store):
    """For every essay cited anywhere, resolve its ISO week once (git add-date).
    Returns {essay_number: iso_week_or_None} and a list of unresolved essays."""
    essays = set()
    for d in store["dispositions"]:
        essays.update(d["evidence"])
    weeks = {}
    unresolved = []
    for e in sorted(essays):
        d, _name = essay_date(e)
        if d:
            weeks[e] = _isoweek(d)
        else:
            weeks[e] = None
            unresolved.append(e)
    return weeks, unresolved


def apply_weeks(store, weeks):
    """Attach an evidence_weeks map (essay -> ISO week) to each disposition.
    Keyed by string essay number so it round-trips through JSON cleanly. Leaves
    the bare-int evidence list untouched — this is a parallel map, the shape
    seed 175 said touches the least other code."""
    stamp = datetime.now(timezone.utc).isoformat()
    for d in store["dispositions"]:
        d["evidence_weeks"] = {
            str(e): weeks.get(e) for e in sorted(d["evidence"])
        }
        d["evidence_weeks_written_at"] = stamp
    return store


def main():
    ap = argparse.ArgumentParser(description="persist evidence write-weeks into the store")
    ap.add_argument("--dry-run", action="store_true", help="print what would be written; mutate nothing")
    args = ap.parse_args()

    store = load_store()
    weeks, unresolved = resolve_weeks(store)

    print("RESOLVED WRITE-WEEKS (git add-date -> ISO week)")
    print("=" * 60)
    for e in sorted(weeks):
        print(f"  essay {e:>3}  {weeks[e] or '(unresolved)'}")
    if unresolved:
        print(f"\nWARNING: {len(unresolved)} essay(s) had no resolvable date: {unresolved}")
        print("These land as null in the store; --independence will skip them,")
        print("which is honest — an unknown week is not a distinct week.")
    print()

    apply_weeks(store, weeks)

    if args.dry_run:
        print("--dry-run: store NOT written. evidence_weeks per disposition:")
        for d in store["dispositions"]:
            print(f"  #{d['id']}: {d['evidence_weeks']}")
        return

    STORE.write_text(json.dumps(store, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote evidence_weeks into {STORE.name} for {len(store['dispositions'])} dispositions.")
    print("No independence score was stored (seed 175): independence stays a read.")


if __name__ == "__main__":
    main()
