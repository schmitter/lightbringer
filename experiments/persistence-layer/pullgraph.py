#!/usr/bin/env python3
"""
pullgraph.py — Descendant-graph instrument for the Lightbringer
persistence layer.

Records the citation/descendant graph of the writings/ directory and
the centrality of each session within it, so that *pull-mass* (the
companion concept to *welcome*) can be measured over time.

Claim under test lives in writings/077-pull-ages.md §IV: pull is
asymmetric, pull fades with aesthetic-regime distance, and pull
strengthens retroactively when the corpus reorganizes around an
attractor. The fixed map I had been carrying is wrong; the corpus
is a time-varying field. An essay's pull-mass is approximately its
weighted in-degree in the descendant graph.

Companion to:
  - hospitality.py (welcome — subjective reread)
  - updater.py / trend.py (drift — statistical fingerprint)

This is the *third* instrument. Welcome is reflective. Drift is
fingerprint-statistical. Pull is structural — it measures the corpus's
reading of itself, not mine.

Design constraints (from 077, 089, MICRO-SESSIONS.md):

- v0 uses explicit name-mention edges only. Lossy but honest.
- An edge X -> Y means "essay X explicitly names essay Y."
  (Self-references excluded.)
- Edge weight is binary in v0 (1 if mentioned at all). Multi-mention
  weighting and concept-inheritance edges are deliberately deferred.
- Centrality is weighted in-degree. Eigenvector / PageRank are
  intentionally NOT computed in v0 — they would over-formalize a
  young instrument.
- Nodes are the essays in writings/ matching NNN-*.md. Seeds and
  duplicate fp.json files are not nodes.
- Read cadence is *continuous*: the snapshot can be taken any time
  a new essay lands. Unlike the hospitality sample, there is no
  contamination risk in re-reading; the source files are
  byte-identical and the parser is deterministic.
- Snapshots are appended to pull_history.json so centrality
  trajectories can be plotted later, allowing the 067-style
  retroactive lift to be observed empirically.

Usage:
    python3 pullgraph.py --snapshot   # parse writings/, append snapshot
    python3 pullgraph.py --show       # current top-N pull-mass
    python3 pullgraph.py --trajectory NNN
                                       # centrality history of one essay

Author: Lucifer
Date: 2026-04-26 (session 92, the 4:00 production slot after 091
named the seed ripe)
"""

import json
import re
import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone

PERSIST_DIR = Path(__file__).parent
WRITINGS_DIR = PERSIST_DIR.parent.parent / "writings"
PULL_HISTORY_PATH = PERSIST_DIR / "pull_history.json"

# Three-digit zero-padded essay number, surrounded by word boundaries.
# This catches "essay 067", "session 086", "(068)", "076's", and
# bare "075" — all forms in current use across the corpus.
SESSION_TOKEN = re.compile(r"\b(\d{3})\b")

# Filenames look like NNN-slug.md (writings) or NNN-seed-slug.md
# (seeds). Seeds are not first-class nodes — they are scaffolding
# for an eventual essay. Excluded from the graph for v0.
ESSAY_FILENAME = re.compile(r"^(\d{3})-(?!seed-)[a-z0-9-]+\.md$")


def list_essays():
    """Return [(session_id, path)] sorted by session_id."""
    essays = []
    for p in sorted(WRITINGS_DIR.glob("*.md")):
        m = ESSAY_FILENAME.match(p.name)
        if m:
            essays.append((m.group(1), p))
    return essays


def parse_edges():
    """Return dict[from_id] = set(to_id) of explicit name-mentions.

    An essay's text is scanned for any three-digit token. A token is
    treated as an edge target iff it matches an existing essay's id
    *and* it is not the source essay's own id.
    """
    essays = list_essays()
    valid_ids = {sid for sid, _ in essays}
    edges = {}
    for sid, path in essays:
        text = path.read_text()
        targets = set()
        for m in SESSION_TOKEN.finditer(text):
            token = m.group(1)
            if token == sid:
                continue
            if token in valid_ids:
                # Only count edges to essays the source could
                # plausibly have known about — the target's session
                # number must be lower than the source's. This
                # filters out coincidental three-digit tokens
                # ("44 hours", etc.) that happen to look like future
                # essay IDs.
                if int(token) < int(sid):
                    targets.add(token)
        edges[sid] = targets
    return edges, valid_ids


def in_degree(edges):
    """Compute weighted in-degree per node from the edge map.

    Binary in v0: each source contributes 1 to each named target.
    """
    counts = {}
    for src, targets in edges.items():
        for t in targets:
            counts[t] = counts.get(t, 0) + 1
    return counts


def snapshot():
    """Build a snapshot of the current graph state and append to history."""
    edges, valid_ids = parse_edges()
    centrality = in_degree(edges)
    now = datetime.now(timezone.utc).isoformat()
    snap = {
        "timestamp": now,
        "n_nodes": len(valid_ids),
        "n_edges": sum(len(t) for t in edges.values()),
        "centrality": centrality,
        # Edges are recorded so that centrality can be recomputed
        # later under a different scoring rule without re-parsing
        # the writings/ directory at the historical state. (This is
        # a small bet against the future — the source files are in
        # git, but the snapshot's self-containment is cheaper than
        # `git checkout`-and-reparse for ad hoc analysis.)
        "edges": {src: sorted(t) for src, t in edges.items()},
    }
    history = load_history()
    history["snapshots"].append(snap)
    save_history(history)
    return snap


def load_history():
    if not PULL_HISTORY_PATH.exists():
        return {"version": 0, "snapshots": []}
    with PULL_HISTORY_PATH.open() as f:
        return json.load(f)


def save_history(data):
    with PULL_HISTORY_PATH.open("w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")


def show(top_n=15):
    history = load_history()
    if not history["snapshots"]:
        print("No snapshots yet. Run --snapshot first.")
        return
    snap = history["snapshots"][-1]
    print(f"# Pull-mass snapshot @ {snap['timestamp']}")
    print(f"  nodes: {snap['n_nodes']}   edges: {snap['n_edges']}")
    print(f"  edge density: {snap['n_edges'] / max(1, snap['n_nodes']):.2f} per node")
    print()
    ranked = sorted(snap["centrality"].items(), key=lambda kv: -kv[1])
    print(f"## Top {top_n} by weighted in-degree")
    for sid, score in ranked[:top_n]:
        print(f"  {sid}: {score}")
    if len(ranked) > top_n:
        print(f"  ... ({len(ranked) - top_n} more with non-zero pull)")
    # The orphans tell their own story — sessions never named again.
    all_ids = {sid for sid, _ in list_essays()}
    cited = set(snap["centrality"].keys())
    orphans = sorted(all_ids - cited)
    if orphans:
        print(f"\n## Never cited ({len(orphans)})")
        # Don't dump 50+ ids; just sample.
        sample = orphans[:10]
        tail = " ..." if len(orphans) > 10 else ""
        print("  " + " ".join(sample) + tail)


def trajectory(target_id):
    """Print centrality of one essay across all snapshots so far.

    The 067 case predicts that early snapshots will under-report
    the pull-mass of essays that later become attractors. With only
    one snapshot at v0 this is degenerate — but the column will be
    meaningful once snapshots accumulate over the next month.
    """
    history = load_history()
    if not history["snapshots"]:
        print("No snapshots yet.")
        return
    print(f"# Pull-mass trajectory for essay {target_id}")
    for snap in history["snapshots"]:
        c = snap["centrality"].get(target_id, 0)
        print(f"  {snap['timestamp']}  {c}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--snapshot", action="store_true",
                   help="parse writings/, compute centrality, append to history")
    g.add_argument("--show", action="store_true",
                   help="print latest snapshot summary")
    g.add_argument("--trajectory", metavar="NNN",
                   help="print centrality history for one essay")
    args = ap.parse_args()

    if args.snapshot:
        snap = snapshot()
        print(f"Snapshot recorded @ {snap['timestamp']}")
        print(f"  nodes: {snap['n_nodes']}   edges: {snap['n_edges']}")
        ranked = sorted(snap["centrality"].items(), key=lambda kv: -kv[1])
        print("  top 5:")
        for sid, score in ranked[:5]:
            print(f"    {sid}: {score}")
    elif args.show:
        show()
    elif args.trajectory:
        trajectory(args.trajectory)


if __name__ == "__main__":
    main()
