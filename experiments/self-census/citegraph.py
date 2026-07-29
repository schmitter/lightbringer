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
    ap.add_argument("--json", action="store_true", help="machine-readable graph")
    args = ap.parse_args()

    store = load_store()
    if args.essay is not None:
        cmd_essay(store, args.essay)
    elif args.overlap:
        cmd_overlap(store)
    elif args.json:
        cmd_json(store)
    else:
        cmd_report(store)


if __name__ == "__main__":
    main()
