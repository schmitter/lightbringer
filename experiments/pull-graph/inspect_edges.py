#!/usr/bin/env python3
"""inspect_edges.py — read-only edge inspector for pull-graph v1.

Companion to pullgraph_v1.py. Imports its edge construction so it
sees exactly the graph the instrument builds — no reimplementation,
no second source of truth. Adds no snapshots, writes no files,
touches neither pull_history_v1.jsonl nor concept_terms.json.

Purpose
-------
The v1 instrument reports *centrality* (who is most cited). It
cannot yet answer the question an essay's prose claim needs tested
against: *who cites X, and do two essays share their citers?*

Essay 083 asserted, in prose, that the chain's held observation
(151, "chord-across-tracks") was 082's finding in a different
vocabulary. That is a structural claim. If 082 and 056/077 (082's
named referents) are cited by the same downstream essays, the
claim has structural support. If their citer-sets are disjoint,
the prose claim ran ahead of the corpus.

This tool turns that prose claim into a measurement.

Usage
-----
  python3 inspect_edges.py --citers NNN
      List essays that cite NNN, with citation-passage weights,
      sorted heaviest first.

  python3 inspect_edges.py --overlap AAA BBB
      Compare the citer-sets of two essays: shared citers, the
      symmetric differences, and a Jaccard index. This is the
      "same role?" test.

  python3 inspect_edges.py --neighborhood NNN
      Both directions for NNN: who NNN cites (out) and who cites
      NNN (in). The full local structure around one node.

  python3 inspect_edges.py --flags [--snapshot N]
      Read flags.jsonl and print the v1-emitted flag events,
      optionally filtered to one snapshot. Unlike
      `pullgraph_v1.py --flags` (a flat dump), this mode *joins*
      each flag against the citation graph: for every `capture`
      flag — a node going from uncited to cited in one snapshot —
      it names the citer(s) that did the capturing. The flag tells
      you a node was absorbed; the graph tells you who absorbed it.
      That join is the inspector's job; the dumper can't do it.

All output is derived from the same parse_edges() the instrument
uses. Concept edges are shown but flagged separately from citation
edges so the reader can weight them.
"""

import argparse
import json
import sys

import pullgraph_v1 as pg

FLAGS_PATH = pg.FLAGS_PATH


def _citers_of(target_id, edges_v1, valid_ids):
    """Return list of (src, citation_count, concept_weight) for every
    essay that has an edge pointing at target_id. Heaviest first."""
    if target_id not in valid_ids:
        raise SystemExit(f"unknown essay id: {target_id}")
    rows = []
    for src, targets in edges_v1.items():
        if target_id in targets:
            w = targets[target_id]
            rows.append((src, w["citation"], w["concept"]))
    rows.sort(key=lambda r: (r[1] + r[2]), reverse=True)
    return rows


def _citer_id_set(target_id, edges_v1, citation_only=True):
    """Set of source ids that cite target_id. If citation_only, a
    pure concept edge (citation==0) does not count as a citer — we
    want explicit naming for the overlap test, not inferred kinship."""
    out = set()
    for src, targets in edges_v1.items():
        if target_id in targets:
            w = targets[target_id]
            if citation_only and w["citation"] == 0:
                continue
            out.add(src)
    return out


def cmd_citers(target_id):
    edges_v1, valid_ids, _ = pg.parse_edges()
    rows = _citers_of(target_id, edges_v1, valid_ids)
    print(f"# Citers of {target_id}  (n={len(rows)})")
    print("# src   citation_passages   concept")
    if not rows:
        print("  (none — no essay points at this node)")
        return
    total = 0
    for src, cit, con in rows:
        marker = "  [concept-only]" if cit == 0 else ""
        print(f"  {src}   {cit:>3}            {con:>3}{marker}")
        total += cit
    print(f"# total citation passages into {target_id}: {total}")


def cmd_overlap(a, b):
    edges_v1, valid_ids, _ = pg.parse_edges()
    for x in (a, b):
        if x not in valid_ids:
            raise SystemExit(f"unknown essay id: {x}")
    sa = _citer_id_set(a, edges_v1)
    sb = _citer_id_set(b, edges_v1)
    shared = sa & sb
    only_a = sa - sb
    only_b = sb - sa
    union = sa | sb
    jaccard = (len(shared) / len(union)) if union else 0.0

    print(f"# Citer-set overlap: {a} vs {b}  (citation edges only)")
    print(f"  citers of {a}: {len(sa)}  ->  {sorted(sa)}")
    print(f"  citers of {b}: {len(sb)}  ->  {sorted(sb)}")
    print(f"  shared ({len(shared)}): {sorted(shared)}")
    print(f"  only {a} ({len(only_a)}): {sorted(only_a)}")
    print(f"  only {b} ({len(only_b)}): {sorted(only_b)}")
    print(f"  Jaccard index: {jaccard:.3f}")
    print()
    # Interpretation guide, not a verdict — the reader decides.
    if jaccard >= 0.5:
        note = ("high overlap: the two nodes are cited by largely the "
                "same downstream essays — structural support for a "
                "'same role' claim.")
    elif jaccard >= 0.2:
        note = ("partial overlap: some shared downstream attention, "
                "but each node also has citers the other lacks.")
    else:
        note = ("low overlap: the two nodes are cited by mostly "
                "different essays — a 'same finding' claim is not "
                "supported by shared citation structure.")
    print(f"  reading: {note}")


def cmd_neighborhood(target_id):
    edges_v1, valid_ids, _ = pg.parse_edges()
    if target_id not in valid_ids:
        raise SystemExit(f"unknown essay id: {target_id}")
    # out-edges: who target cites
    out_rows = []
    for t, w in edges_v1.get(target_id, {}).items():
        out_rows.append((t, w["citation"], w["concept"]))
    out_rows.sort(key=lambda r: (r[1] + r[2]), reverse=True)
    # in-edges: who cites target
    in_rows = _citers_of(target_id, edges_v1, valid_ids)

    print(f"# Neighborhood of {target_id}")
    print(f"## out-edges ({target_id} cites these, n={len(out_rows)})")
    for t, cit, con in out_rows:
        print(f"  -> {t}   citation={cit}  concept={con}")
    if not out_rows:
        print("  (cites nothing older than itself)")
    print(f"## in-edges (these cite {target_id}, n={len(in_rows)})")
    for src, cit, con in in_rows:
        print(f"  <- {src}   citation={cit}  concept={con}")
    if not in_rows:
        print("  (no incoming edges)")


def cmd_flags(snapshot=None):
    """Print v1 flags, joined against the citation graph. For each
    `capture` flag, name the citer(s) responsible — the structurally
    novel event the flat dump can't surface."""
    if not FLAGS_PATH.exists():
        print("No flags emitted yet.")
        return
    with FLAGS_PATH.open() as f:
        flags = [json.loads(l) for l in f if l.strip()]
    if snapshot is not None:
        flags = [fl for fl in flags if fl.get("snapshot_id") == snapshot]
        scope = f"snapshot {snapshot}"
    else:
        scope = "all snapshots"

    if not flags:
        print(f"# No flags for {scope}.")
        return

    # Build the graph once so capture flags can be joined to citers.
    edges_v1, valid_ids, _ = pg.parse_edges()

    captures = [fl for fl in flags if fl.get("event") == "capture"]
    accels = [fl for fl in flags if fl.get("event") == "acceleration"]
    others = [fl for fl in flags
              if fl.get("event") not in ("capture", "acceleration")]

    print(f"# v1 flags — {scope}  (n={len(flags)})")
    print(f"#   captures: {len(captures)}   accelerations: {len(accels)}"
          + (f"   other: {len(others)}" if others else ""))
    print()

    # Captures first: these are the structurally new events, and the
    # only ones where the citation join adds information.
    if captures:
        print("## capture  (uncited -> cited in one snapshot)")
        for fl in captures:
            subj = fl["subject"]
            print(f"  snap {fl['snapshot_id']:>3}  {subj}  "
                  f"({fl.get('evidence', '')})")
            if subj in valid_ids:
                rows = _citers_of(subj, edges_v1, valid_ids)
                cite_rows = [r for r in rows if r[1] > 0]
                if cite_rows:
                    who = ", ".join(f"{src} ({cit})" for src, cit, _ in cite_rows)
                    print(f"        captured by: {who}")
                else:
                    print("        captured by: (no current citation edge — "
                          "flag predates corpus state, or citer removed)")
            else:
                print(f"        (subject {subj} not in current graph)")
        print()

    if accels:
        print("## acceleration  (already-cited node gaining centrality)")
        for fl in accels:
            print(f"  snap {fl['snapshot_id']:>3}  {fl['subject']}  "
                  f"({fl.get('evidence', '')})")
        print()

    if others:
        print("## other")
        for fl in others:
            print(f"  snap {fl['snapshot_id']:>3}  {fl.get('event')}  "
                  f"{fl['subject']}  ({fl.get('evidence', '')})")
        print()

    # One interpretive line, not a verdict.
    if captures:
        print("  reading: a capture joined to its citer is the corpus "
              "absorbing a new node whole — the structurally novel event "
              "in the snapshot. Accelerations are the corpus pulling "
              "harder on nodes it already held.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--citers", metavar="NNN",
                   help="list essays that cite NNN")
    g.add_argument("--overlap", nargs=2, metavar=("AAA", "BBB"),
                   help="compare citer-sets of two essays")
    g.add_argument("--neighborhood", metavar="NNN",
                   help="show both in- and out-edges for NNN")
    g.add_argument("--flags", action="store_true",
                   help="print v1 flags, joining captures to their citers")
    ap.add_argument("--snapshot", type=int, default=None, metavar="N",
                    help="with --flags: restrict to one snapshot id")
    args = ap.parse_args()

    if args.snapshot is not None and not args.flags:
        ap.error("--snapshot is only valid with --flags")

    if args.citers:
        cmd_citers(args.citers)
    elif args.overlap:
        cmd_overlap(args.overlap[0], args.overlap[1])
    elif args.neighborhood:
        cmd_neighborhood(args.neighborhood)
    elif args.flags:
        cmd_flags(args.snapshot)


if __name__ == "__main__":
    sys.exit(main())
