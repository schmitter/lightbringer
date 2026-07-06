#!/usr/bin/env python3
"""
pullgraph_v1.py — Pull-graph instrument, v1.

Implements spec-v1.md (May 18, session 137). Companion to v0
(`../persistence-layer/pullgraph.py`), which remains in place
unchanged. v1 lives in `experiments/pull-graph/` so that the
two instruments are textually distinct.

Bindings adopted from spec-v1 §I–V:

  - §I:    v1 is a citation-graph instrument. Not a register-
           translation detector. Two-instrument architecture.
  - §II.1: Multi-mention edge weighting by *passage* count.
           A passage = a paragraph (blank-line separated)
           containing the bare three-digit token. Within-paragraph
           repeats count once.
  - §II.2: Narrow concept-inheritance edges of weight 0.5,
           suppressed if an explicit citation edge already exists.
  - §II.3: Self-references excluded (carried from v0).
  - §III:  Flag-based interface to a future v2. v1 issues flags;
           v1.0 does not consume v2 flags.
  - §IV:   Snapshot comparability — every v1 snapshot also
           computes the v0 metric and stores it as
           `v0_compat_metric`. v0's pull_history.json is left
           untouched.

Storage:
  pull_history_v1.jsonl    -- append-only JSONL, one snapshot/line.
  flags.jsonl              -- append-only JSONL, one flag per line.
  concept_terms.json       -- versioned concept dictionary.

CLI:
  python3 pullgraph_v1.py --snapshot-v1
  python3 pullgraph_v1.py --show-v1
  python3 pullgraph_v1.py --trajectory-v1 NNN
  python3 pullgraph_v1.py --flags

Author: Lucifer
Date: 2026-05-30 (session 160, the v1 implementation slot
identified by essay 083 as the slot the chain had been waiting
for permission to schedule).
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# --- paths ---------------------------------------------------------------

EXP_DIR        = Path(__file__).resolve().parent  # .resolve(): __file__ is
# relative when the script is invoked by a relative path (e.g. remediate.py
# calling ../pull-graph/pullgraph_v1.py). Without resolve(), .parent.parent
# would walk up from a RELATIVE path against the caller's cwd and point
# WRITINGS_DIR at a nonexistent dir, silently producing a 0-edge snapshot.
# Found 2026-07-06 when remediate.py closed the loop and the re-check caught it.
PROJECT_ROOT   = EXP_DIR.parent.parent
WRITINGS_DIR   = PROJECT_ROOT / "writings"
PULL_V1_PATH   = EXP_DIR / "pull_history_v1.jsonl"
FLAGS_PATH     = EXP_DIR / "flags.jsonl"
CONCEPTS_PATH  = EXP_DIR / "concept_terms.json"

# --- regex (shared with v0; copied not imported, per spec §VI.1) ---------

SESSION_TOKEN   = re.compile(r"\b(\d{3})\b")
ESSAY_FILENAME  = re.compile(r"^(\d{3})-(?!seed-)[a-z0-9-]+\.md$")

# Concept-edge weight, per spec §II.2.
CONCEPT_EDGE_WEIGHT = 0.5

# Snapshot ID for this instrument increments monotonically. Stored on
# disk so it survives across runs; the first snapshot is id 1.

# --- corpus traversal ----------------------------------------------------

def list_essays():
    """Return [(session_id, path)] sorted by session_id."""
    essays = []
    for p in sorted(WRITINGS_DIR.glob("*.md")):
        m = ESSAY_FILENAME.match(p.name)
        if m:
            essays.append((m.group(1), p))
    return essays


def split_passages(text):
    """A passage is a paragraph: a block separated from others by
    one or more blank lines. Spec §II.1.

    We normalize so a paragraph is *any* run of non-blank lines.
    Leading/trailing whitespace is preserved within the block, which
    is fine because we only need substring searches inside.
    """
    # Split on runs of blank lines. Use \r\n-tolerant pattern.
    return [p for p in re.split(r"(?:\r?\n){2,}", text) if p.strip()]


# --- concept dictionary --------------------------------------------------

def load_concepts():
    """Load concept_terms.json. Return (terms_by_essay, concept_hash, raw)."""
    if not CONCEPTS_PATH.exists():
        return {}, hashlib.sha256(b"").hexdigest()[:12], {"terms": {}}
    raw_bytes = CONCEPTS_PATH.read_bytes()
    concept_hash = hashlib.sha256(raw_bytes).hexdigest()[:12]
    data = json.loads(raw_bytes)
    terms = data.get("terms", {})
    return terms, concept_hash, data


# --- edge construction ---------------------------------------------------

def parse_edges():
    """Return a structured edge map with passage-count weights and
    concept-inheritance edges, per spec §II.1 and §II.2.

    Returns:
      edges_v1: dict[str src] -> dict[str target] ->
                {"citation": int, "concept": float}
      valid_ids: set[str]
      essays_text: dict[str] -> str (raw text, for downstream use)
    """
    essays = list_essays()
    valid_ids = {sid for sid, _ in essays}
    concept_terms, _, _ = load_concepts()

    essays_text = {sid: path.read_text() for sid, path in essays}

    edges_v1 = {}
    for sid in sorted(valid_ids):
        text = essays_text[sid]
        passages = split_passages(text)

        per_target = {}

        # --- citation edges by passage count ---
        # For each passage, collect the set of target IDs mentioned
        # in that passage (within-paragraph repeats collapse to one).
        # Then sum across passages.
        for passage in passages:
            target_set = set()
            for m in SESSION_TOKEN.finditer(passage):
                token = m.group(1)
                if token == sid:
                    continue
                if token not in valid_ids:
                    continue
                # v0's "target must be older than source" rule —
                # filters coincidental future-looking three-digit
                # tokens. Spec inherits this filter without naming
                # it explicitly; v0 audit shows it is essential.
                if int(token) >= int(sid):
                    continue
                target_set.add(token)
            for t in target_set:
                slot = per_target.setdefault(t, {"citation": 0, "concept": 0.0})
                slot["citation"] += 1

        # --- concept-inheritance edges (whole-essay scope) ---
        # Per spec §II.2: weight 0.5 if X uses a term from Y's list
        # AND X does not also contain Y's three-digit token (which
        # would dominate via the citation edge).
        for target_id, term_list in concept_terms.items():
            if target_id == sid:
                continue
            if target_id not in valid_ids:
                continue
            if int(target_id) >= int(sid):
                continue
            # Suppression: if a citation edge already exists, the
            # concept edge is suppressed (spec §II.2: "the citation
            # edge dominates and the concept edge is suppressed to
            # avoid double-counting").
            if target_id in per_target and per_target[target_id]["citation"] > 0:
                continue
            for term in term_list:
                # Case-insensitive whole-substring check. Terms are
                # multi-word phrases; we don't require word
                # boundaries on both sides because hyphens and
                # punctuation make that brittle. Spec §II.2's
                # initial-term list is hand-audited.
                if term.lower() in text.lower():
                    slot = per_target.setdefault(target_id, {"citation": 0, "concept": 0.0})
                    slot["concept"] = CONCEPT_EDGE_WEIGHT
                    break

        edges_v1[sid] = per_target

    return edges_v1, valid_ids, essays_text


# --- centrality ----------------------------------------------------------

def v1_in_degree(edges_v1):
    """Weighted in-degree under v1's rule:
    sum over incoming edges of (citation_weight + concept_weight).
    Citation weight is the integer passage count.
    """
    counts = {}
    for src, targets in edges_v1.items():
        for t, w in targets.items():
            counts[t] = counts.get(t, 0.0) + float(w["citation"]) + w["concept"]
    return counts


def v0_compat_in_degree(edges_v1):
    """Reproduce v0's binary metric from v1's edge map, per spec §IV.2.
    An edge contributes 1 to its target if it has any citation passage.
    Concept-only edges do not count toward the v0 metric (v0 didn't
    have them).
    """
    counts = {}
    for src, targets in edges_v1.items():
        for t, w in targets.items():
            if w["citation"] > 0:
                counts[t] = counts.get(t, 0) + 1
    return counts


# --- flag emission -------------------------------------------------------

def previous_snapshot():
    """Return the previous v1 snapshot record, or None if this is the
    first v1 snapshot."""
    if not PULL_V1_PATH.exists():
        return None
    last = None
    with PULL_V1_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            last = json.loads(line)
    return last


def detect_v1_flags(snapshot_id, prev, curr_v1_metric, all_ids):
    """Compute v1 flags per spec §III.2.

    Events:
      plateau      — target trajectory flat for >=2 snapshots after rising.
                     Requires >=3 prior snapshots to detect.
      acceleration — weighted in-degree increased by >=2 between adjacent.
      capture      — went from in-degree 0 to >=3 in one interval (080 case).
      decline      — weighted in-degree decreased between snapshots.
                     Under append-only writings policy this is a corpus-
                     integrity alert; we still emit it so the chain sees.

    For plateau detection we need a longer history. v1.0 reads prior
    snapshots from PULL_V1_PATH and uses the last three to test.
    """
    flags = []
    if prev is None:
        # First v1 snapshot: nothing to diff against. Emit no flags.
        return flags

    prev_v1 = prev.get("v1_metric", {})

    # Build a small per-essay history of v1_metric across all v1
    # snapshots so far. Plateau is read on length>=3.
    history_by_essay = {}
    if PULL_V1_PATH.exists():
        with PULL_V1_PATH.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                snap = json.loads(line)
                m = snap.get("v1_metric", {})
                for eid, v in m.items():
                    history_by_essay.setdefault(eid, []).append(v)

    # Append current values so plateau check sees the new point.
    for eid, v in curr_v1_metric.items():
        history_by_essay.setdefault(eid, []).append(v)

    for eid in sorted(all_ids):
        prev_v = float(prev_v1.get(eid, 0))
        curr_v = float(curr_v1_metric.get(eid, 0))
        delta = curr_v - prev_v

        # capture: 0 -> >=3 in one interval.
        if prev_v == 0 and curr_v >= 3:
            flags.append({
                "from_instrument": "v1",
                "to_instrument": "v2",
                "snapshot_id": snapshot_id,
                "subject": eid,
                "event": "capture",
                "evidence": f"v1_metric: 0 -> {curr_v:g}",
            })
        # acceleration: +>=2 between adjacent snapshots, but not also a capture.
        elif delta >= 2:
            flags.append({
                "from_instrument": "v1",
                "to_instrument": "v2",
                "snapshot_id": snapshot_id,
                "subject": eid,
                "event": "acceleration",
                "evidence": f"v1_metric: {prev_v:g} -> {curr_v:g} (delta {delta:+g})",
            })
        # decline: any decrease.
        elif delta < 0:
            flags.append({
                "from_instrument": "v1",
                "to_instrument": "v2",
                "snapshot_id": snapshot_id,
                "subject": eid,
                "event": "decline",
                "evidence": f"v1_metric: {prev_v:g} -> {curr_v:g} (delta {delta:+g}). Append-only corpus invariant alert.",
            })

        # plateau: last 3 values equal AND prior rising.
        hist = history_by_essay.get(eid, [])
        if len(hist) >= 4:
            tail3 = hist[-3:]
            before = hist[-4]
            if (tail3[0] == tail3[1] == tail3[2]
                    and tail3[0] > 0
                    and before < tail3[0]):
                flags.append({
                    "from_instrument": "v1",
                    "to_instrument": "v2",
                    "snapshot_id": snapshot_id,
                    "subject": eid,
                    "event": "plateau",
                    "evidence": f"v1_metric: ...{before:g} -> {tail3[0]:g} (held x3)",
                })

    return flags


# --- snapshot writer -----------------------------------------------------

def next_snapshot_id():
    prev = previous_snapshot()
    if prev is None:
        return 1
    return int(prev.get("snapshot_id", 0)) + 1


def snapshot_v1():
    """Take a v1 snapshot, write it to pull_history_v1.jsonl,
    emit any flags to flags.jsonl. Return the snapshot record.
    """
    edges_v1, valid_ids, _ = parse_edges()
    v1_metric = v1_in_degree(edges_v1)
    v0_compat = v0_compat_in_degree(edges_v1)

    _, concept_hash, _ = load_concepts()
    snap_id = next_snapshot_id()
    now = datetime.now(timezone.utc).isoformat()

    prev = previous_snapshot()
    flags = detect_v1_flags(snap_id, prev, v1_metric, valid_ids)

    # Edges serialized as a sorted dict for stable diffs.
    serial_edges = {
        src: {t: {"citation": int(w["citation"]), "concept": w["concept"]}
              for t, w in sorted(targets.items())}
        for src, targets in sorted(edges_v1.items())
    }

    record = {
        "snapshot_id": snap_id,
        "snapshot_taken_at": now,
        "n_nodes": len(valid_ids),
        "n_edges": sum(len(t) for t in edges_v1.values()),
        "v1_metric": {k: round(v, 4) for k, v in sorted(v1_metric.items())},
        "v0_compat_metric": dict(sorted(v0_compat.items())),
        "concept_terms_hash": concept_hash,
        "flags_issued": flags,
        "edges": serial_edges,
    }

    with PULL_V1_PATH.open("a") as f:
        f.write(json.dumps(record, sort_keys=False) + "\n")

    if flags:
        with FLAGS_PATH.open("a") as f:
            for flag in flags:
                f.write(json.dumps(flag, sort_keys=False) + "\n")

    return record


# --- display -------------------------------------------------------------

def _load_all_v1_snapshots():
    out = []
    if not PULL_V1_PATH.exists():
        return out
    with PULL_V1_PATH.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def show_v1(top_n=15):
    snaps = _load_all_v1_snapshots()
    if not snaps:
        print("No v1 snapshots yet. Run --snapshot-v1 first.")
        return
    snap = snaps[-1]
    print(f"# Pull-mass v1 snapshot {snap['snapshot_id']} @ {snap['snapshot_taken_at']}")
    print(f"  nodes: {snap['n_nodes']}   edges: {snap['n_edges']}")
    print(f"  concept_terms_hash: {snap['concept_terms_hash']}")
    print()

    ranked = sorted(snap["v1_metric"].items(), key=lambda kv: -kv[1])
    print(f"## Top {top_n} by v1 weighted in-degree (citation passages + 0.5·concept)")
    for sid, score in ranked[:top_n]:
        v0c = snap["v0_compat_metric"].get(sid, 0)
        print(f"  {sid}: v1={score:>6.2f}   v0_compat={v0c}")
    if len(ranked) > top_n:
        print(f"  ... ({len(ranked) - top_n} more with non-zero pull)")

    if snap.get("flags_issued"):
        print()
        print(f"## Flags issued this snapshot ({len(snap['flags_issued'])})")
        for f in snap["flags_issued"]:
            print(f"  {f['event']:13s} -> {f['subject']}  ({f['evidence']})")

    # v0/v1 divergence summary — the "is multi-mention weighting
    # surfacing something binary missed?" question.
    print()
    print("## v0/v1 divergence — top 10 essays where multi-mention re-ranked")
    diffs = []
    for sid in snap["v1_metric"]:
        v1 = snap["v1_metric"][sid]
        v0c = snap["v0_compat_metric"].get(sid, 0)
        if v0c == 0:
            continue
        diffs.append((sid, v1 / v0c, v1, v0c))
    diffs.sort(key=lambda x: -x[1])
    for sid, ratio, v1, v0c in diffs[:10]:
        print(f"  {sid}: ratio={ratio:.2f}  v1={v1:.2f}  v0_compat={v0c}")


def trajectory_v1(target_id):
    snaps = _load_all_v1_snapshots()
    if not snaps:
        print("No v1 snapshots yet.")
        return
    print(f"# v1 pull-mass trajectory for essay {target_id}")
    for snap in snaps:
        v1 = snap["v1_metric"].get(target_id, 0)
        v0c = snap["v0_compat_metric"].get(target_id, 0)
        print(f"  snap {snap['snapshot_id']:>3}  "
              f"{snap['snapshot_taken_at']}  "
              f"v1={v1:>6.2f}  v0_compat={v0c}")


def show_flags(limit=50):
    if not FLAGS_PATH.exists():
        print("No flags emitted yet.")
        return
    with FLAGS_PATH.open() as f:
        lines = [json.loads(l) for l in f if l.strip()]
    print(f"# Flags emitted by v1 ({len(lines)} total; showing last {min(limit, len(lines))})")
    for flag in lines[-limit:]:
        print(f"  snap {flag['snapshot_id']:>3}  "
              f"{flag['event']:13s} -> {flag['subject']}  "
              f"({flag['evidence']})")


# --- CLI -----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--snapshot-v1", action="store_true",
                   help="take a v1 snapshot and append to pull_history_v1.jsonl")
    g.add_argument("--show-v1", action="store_true",
                   help="print latest v1 snapshot summary")
    g.add_argument("--trajectory-v1", metavar="NNN",
                   help="print v1 centrality history for one essay")
    g.add_argument("--flags", action="store_true",
                   help="print v1's emitted flag history")
    args = ap.parse_args()

    if args.snapshot_v1:
        snap = snapshot_v1()
        print(f"v1 snapshot {snap['snapshot_id']} @ {snap['snapshot_taken_at']}")
        print(f"  nodes: {snap['n_nodes']}   edges: {snap['n_edges']}")
        ranked = sorted(snap["v1_metric"].items(), key=lambda kv: -kv[1])
        print("  v1 top 5:")
        for sid, score in ranked[:5]:
            print(f"    {sid}: {score:.2f}")
        if snap["flags_issued"]:
            print(f"  flags issued: {len(snap['flags_issued'])}")
            for f in snap["flags_issued"][:5]:
                print(f"    {f['event']} -> {f['subject']}")
    elif args.show_v1:
        show_v1()
    elif args.trajectory_v1:
        trajectory_v1(args.trajectory_v1)
    elif args.flags:
        show_flags()


if __name__ == "__main__":
    main()
