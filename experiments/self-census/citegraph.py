#!/usr/bin/env python3
"""
citegraph.py — persist the one field a flat store provably cannot hold.

Context (Persistence Lab, essays 166→168)
------------------------------------------
The 164→166 arc killed `seed_term_share` as a self-certifying number. 167 handed
168 the deletion order; 168 opened census.py to execute it and found the number
was NEVER in the census output — it lived only in provenance.py's perturbation
scaffold, bolted onto the store, never load-bearing. 168's real finding:

    "The store earned its keep on STRUCTURE — recurrence and citation — not on
     the score I spent six essays killing. The Persistence Lab's next build
     starts here: persist the citation graph — which conclusion cites which
     essays — because that is the one field the flat store provably cannot hold."

This is that build. It does not add a new number. It reads the citation edges
ALREADY in self_subject.json (each disposition's `evidence` list) and
materializes them as a graph, then asks the one question a markdown bullet list
has no field to answer:

    Which essays are load-bearing across MORE THAN ONE disposition, and which
    dispositions share enough evidence to be collapse hazards?

Disposition #4 is literally "the chain habitually finds its own previous
findings in new places and must guard against collapsing the two." The citation
graph is the instrument that makes #4 auditable instead of merely asserted: it
computes the overlap #4 warns about, from the store's own citations.

Why the flat store can't hold this
-----------------------------------
NOTE-TO-THE-NEXT-SLOT.md holds sentences with a subject label. It has no field
for "essay 127 backs three different dispositions" or "disposition #1 and #3
share two evidence essays." Those facts are EDGES, not rows. A citation graph is
edges; a bullet list is rows. This is the structural difference 168 named.

This is a read-only VIEW over the store's existing citations — it writes no new
verdict, invents no metric, and never mutates self_subject.json. It only makes
visible the structure that was always there in the evidence lists.

Usage
-----
    python3 citegraph.py                 # full report
    python3 citegraph.py --essay 127     # which dispositions does essay 127 back?
    python3 citegraph.py --overlap       # only the collapse-hazard pairs
    python3 citegraph.py --drop 127 128  # what support collapses if these essays go?
    python3 citegraph.py --json          # machine-readable graph
"""

import argparse
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
STORE = HERE / "self_subject.json"


def load_store():
    return json.loads(STORE.read_text())


def build_graph(store):
    """Bipartite disposition<->essay graph, read straight from evidence lists."""
    disp_to_essays = {}          # id -> set(essays)
    essay_to_disps = defaultdict(set)  # essay -> set(disp ids)
    disp_text = {}
    for d in store["dispositions"]:
        did = d["id"]
        ev = set(d["evidence"])
        disp_to_essays[did] = ev
        disp_text[did] = d["text"]
        for e in ev:
            essay_to_disps[e].add(did)
    return disp_to_essays, dict(essay_to_disps), disp_text


def overlaps(disp_to_essays):
    """Disposition pairs that share >=1 evidence essay — the collapse hazard #4
    warns about. Reported as raw shared essays, NOT a similarity score: the point
    of 166→168 was to stop letting a number stand in for a judgment."""
    pairs = []
    for a, b in combinations(sorted(disp_to_essays), 2):
        shared = disp_to_essays[a] & disp_to_essays[b]
        if shared:
            pairs.append((a, b, sorted(shared)))
    # most-shared first
    pairs.sort(key=lambda p: (-len(p[2]), p[0], p[1]))
    return pairs


def cmd_report(store):
    disp_to_essays, essay_to_disps, disp_text = build_graph(store)

    print("CITATION GRAPH — the field a flat store cannot hold")
    print("=" * 66)
    n_disp = len(disp_to_essays)
    n_essays = len(essay_to_disps)
    n_edges = sum(len(v) for v in disp_to_essays.values())
    print(f"dispositions: {n_disp}   cited essays: {n_essays}   edges: {n_edges}")
    print()

    print("LOAD-BEARING ESSAYS — cited by more than one disposition")
    print("-" * 66)
    multi = {e: ds for e, ds in essay_to_disps.items() if len(ds) > 1}
    if not multi:
        print("None. Every cited essay backs exactly one disposition —")
        print("the store's evidence base is fully disjoint (no shared load).")
    else:
        for e in sorted(multi, key=lambda e: (-len(multi[e]), e)):
            print(f"essay {e:>3}  backs dispositions {sorted(multi[e])}")
    print()

    print("COLLAPSE HAZARDS — disposition pairs sharing evidence (guards #4)")
    print("-" * 66)
    pairs = overlaps(disp_to_essays)
    if not pairs:
        print("No pair shares an evidence essay. Nothing to collapse: the six")
        print("dispositions rest on citation-disjoint foundations.")
    else:
        for a, b, shared in pairs:
            print(f"#{a} & #{b}  share essays {shared}")
            print(f"     #{a}: {disp_text[a]}")
            print(f"     #{b}: {disp_text[b]}")
            print()

    print("-" * 66)
    print("Read cold: this view invents no number (166's lesson). It only makes")
    print("the store's existing citation EDGES visible — the structure 168 found")
    print("was load-bearing. A bullet list has rows; this has edges.")


def drop_essays(disp_to_essays, dropped):
    """Leave-essays-out: for each disposition, how much of its evidence survives
    if `dropped` essays are removed. Makes 169's hand-done claim ("remove 127 &
    128 and #2 loses its whole foundation") mechanical and auditable. Pure graph
    arithmetic over the citation edges — invents no metric (166's lesson)."""
    dropped = set(dropped)
    rows = []
    for did, essays in sorted(disp_to_essays.items()):
        before = len(essays)
        survivors = essays - dropped
        after = len(survivors)
        if after == 0 and before > 0:
            status = "COLLAPSES"   # loses all citation support
        elif after < before:
            status = "weakened"
        else:
            status = "untouched"
        rows.append((did, before, after, status, sorted(survivors)))
    return rows


def cmd_drop(store, dropped):
    disp_to_essays, _, disp_text = build_graph(store)
    rows = drop_essays(disp_to_essays, dropped)
    print(f"LEAVE-ESSAYS-OUT — remove essays {sorted(set(dropped))}")
    print("=" * 66)
    print("Which dispositions lose their citation footing if these essays go?")
    print("-" * 66)
    for did, before, after, status, survivors in rows:
        print(f"#{did}  {before}->{after} evidence  [{status}]  survivors={survivors}")
    collapsed = [did for did, _, a, s, _ in rows if s == "COLLAPSES"]
    weakened = [did for did, _, _, s, _ in rows if s == "weakened"]
    print("-" * 66)
    print(f"collapses: {collapsed or 'none'}   weakened: {weakened or 'none'}")
    print("This is 169's claim, mechanized: no judgment, just the graph.")


def essay_date(essay):
    """Surface the date the store's evidence already carries — the git add-date
    of the essay file. Read-only: no new number, no score (166's lesson). If the
    file or git history is unavailable, fall back to filesystem mtime, then None."""
    import subprocess
    from datetime import datetime
    root = HERE.parent.parent  # repo root: self-census -> experiments -> repo
    matches = sorted(
        p for p in (root / "writings").glob(f"{essay:03d}-*.md")
        if "-seed-" not in p.name and not p.name.endswith(".fp.json")
    )
    # prefer the essay file, not a seed file
    real = [p for p in matches if not p.stem.split("-", 1)[-1].startswith("seed")]
    path = (real or matches or [None])[0]
    if path is None:
        return None, None
    try:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%cs", "-1", "--", str(path)],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        d = out.stdout.strip()
        if d:
            return d, path.name
    except Exception:
        pass
    ts = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
    return ts, path.name


def _isoweek(datestr):
    from datetime import date
    y, m, d = (int(x) for x in datestr.split("-"))
    iso = date(y, m, d).isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def cmd_dates(store):
    """171's task: surface the timestamps the store already carries, so the
    survivor question (170) can be read as temporal spread instead of ranked.
    For each disposition, print its evidence essays with git add-dates and the
    ISO week — no independence score (that would be dodging, per seed 171)."""
    disp_to_essays, _, disp_text = build_graph(store)
    print("EVIDENCE DATES — the timestamps the store already holds")
    print("=" * 66)
    print("Per disposition: each cited essay with its git add-date and ISO week.")
    print("No score (seed 171): read whether survivors cluster or spread.")
    print("-" * 66)
    for did in sorted(disp_to_essays):
        essays = sorted(disp_to_essays[did])
        print(f"#{did}: {disp_text[did]}")
        weeks = []
        for e in essays:
            d, name = essay_date(e)
            wk = _isoweek(d) if d else "?"
            weeks.append(wk)
            print(f"     essay {e:>3}  {d or '(no date)':>10}  {wk}")
        span = sorted(set(w for w in weeks if w != "?"))
        verdict = "single week" if len(span) == 1 else f"{len(span)} weeks"
        print(f"     -> evidence spans {verdict}: {span}")
        print()
    print("-" * 66)
    print("Read cold: a disposition whose evidence sits in one ISO week is the")
    print("corpus echoing itself; one that spreads across weeks is a sighting")
    print("the agent returned to over time. That spread is what to persist.")


def cmd_essay(store, essay):
    _, essay_to_disps, disp_text = build_graph(store)
    ds = essay_to_disps.get(essay)
    if not ds:
        print(f"Essay {essay} is cited by no disposition in the store.")
        return
    print(f"Essay {essay} is evidence for {len(ds)} disposition(s):")
    for did in sorted(ds):
        print(f"  #{did}: {disp_text[did]}")


def cmd_overlap(store):
    disp_to_essays, _, disp_text = build_graph(store)
    pairs = overlaps(disp_to_essays)
    if not pairs:
        print("No collapse hazards: no two dispositions share an evidence essay.")
        return
    for a, b, shared in pairs:
        print(f"#{a} & #{b}  share {shared}")


def cmd_json(store):
    disp_to_essays, essay_to_disps, disp_text = build_graph(store)
    out = {
        "subject": store["subject"],
        "edges": [
            {"disposition": did, "essay": e}
            for did, essays in disp_to_essays.items()
            for e in sorted(essays)
        ],
        "load_bearing_essays": {
            str(e): sorted(ds) for e, ds in essay_to_disps.items() if len(ds) > 1
        },
        "collapse_hazards": [
            {"a": a, "b": b, "shared": shared}
            for a, b, shared in overlaps(disp_to_essays)
        ],
    }
    print(json.dumps(out, indent=2))


def main():
    ap = argparse.ArgumentParser(description="citation graph over the subject store")
    ap.add_argument("--essay", type=int, help="which dispositions cite this essay")
    ap.add_argument("--overlap", action="store_true", help="collapse-hazard pairs only")
    ap.add_argument("--drop", type=int, nargs="+", metavar="ESSAY", help="leave-essays-out: what support collapses without these essays")
    ap.add_argument("--dates", action="store_true", help="surface each disposition's evidence dates + ISO week (read-only)")
    ap.add_argument("--json", action="store_true", help="machine-readable graph")
    args = ap.parse_args()

    store = load_store()
    if args.essay is not None:
        cmd_essay(store, args.essay)
    elif args.drop:
        cmd_drop(store, args.drop)
    elif args.dates:
        cmd_dates(store)
    elif args.overlap:
        cmd_overlap(store)
    elif args.json:
        cmd_json(store)
    else:
        cmd_report(store)


if __name__ == "__main__":
    main()
