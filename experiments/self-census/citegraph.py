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


def _week_ordinal(isoweek):
    """Monotonic week index from an 'YYYY-Www' label, so spans subtract cleanly.
    All the corpus lives in 2026, but this stays correct across a year boundary
    by counting whole ISO weeks since an epoch year."""
    y, w = isoweek.split("-W")
    return int(y) * 53 + int(w)


def cmd_spread(store):
    """173's task: express the temporal-spread field 172 read by eye as one
    integer the store already holds. For each disposition, compute the ISO-week
    span (max_week - min_week) and the count of DISTINCT weeks its evidence
    touches. No ranking of dispositions against each other (seed 173: measure
    the one committed prediction, don't leaderboard the corpus)."""
    disp_to_essays, _, disp_text = build_graph(store)
    print("EVIDENCE SPREAD — temporal independence as one integer")
    print("=" * 66)
    print("Per disposition: ISO-week span (max-min) and distinct-week count.")
    print("Span 0 / 1 distinct week = evidence written in one sitting (echo).")
    print("-" * 66)
    results = {}
    for did in sorted(disp_to_essays):
        essays = sorted(disp_to_essays[did])
        weeks = []
        for e in essays:
            d, _ = essay_date(e)
            if d:
                weeks.append(_isoweek(d))
        distinct = sorted(set(weeks))
        if distinct:
            ords = [_week_ordinal(w) for w in distinct]
            span = max(ords) - min(ords)
        else:
            span = 0
        results[did] = (span, len(distinct), distinct)
        print(f"#{did}: span={span}w  distinct_weeks={len(distinct)}  {distinct}")
        print(f"     {disp_text[did]}")
        print()
    print("-" * 66)
    print("172's committed prediction: #5 and #6 rest on a single ISO week")
    print("(span 0, distinct 1) despite sounding most confident; #1 spreads.")
    print("Measured, not eyeballed:")
    for did in (1, 2, 5, 6):
        if did in results:
            span, nd, _ = results[did]
            print(f"     #{did}: span={span}w  distinct_weeks={nd}")
    return results


def cmd_independence(store):
    """175's task: read a disposition's independence as its distinct-write-week
    count STRAIGHT FROM THE STORE — zero git, zero filesystem. This consumes the
    `evidence_weeks` map persist_weeks.py wrote. It is the store answering the
    independence question by itself, where `--spread` re-derives the same number
    from git history on every run.

    Then it proves the two agree: for each disposition it compares the
    store-backed distinct-week count against the git-backed one from cmd_spread.
    If they disagree, the store's provenance is wrong and THAT is the finding
    (seed 175: name it, don't average)."""
    missing = [d["id"] for d in store["dispositions"] if "evidence_weeks" not in d]
    if missing:
        print("Store has no evidence_weeks yet for dispositions:", missing)
        print("Run:  python3 persist_weeks.py   then re-run --independence.")
        return None

    print("INDEPENDENCE — distinct write-weeks, read from the store")
    print("=" * 66)
    print("Store-backed: zero git calls. Independence = len(distinct weeks).")
    print("Null to beat is 1 — evidence inside a single week is an echo.")
    print("-" * 66)
    store_counts = {}
    for d in sorted(store["dispositions"], key=lambda x: x["id"]):
        did = d["id"]
        weeks = [w for w in d["evidence_weeks"].values() if w]
        distinct = sorted(set(weeks))
        store_counts[did] = len(distinct)
        print(f"#{did}: distinct_weeks={len(distinct)}  {distinct}")
    print()

    # Cross-check against the git-backed spread view — the two must agree.
    print("CROSS-CHECK — store-backed vs git-backed (--spread)")
    print("-" * 66)
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        git_results = cmd_spread(store)  # {did: (span, n_distinct, weeks)}
    all_agree = True
    for did in sorted(store_counts):
        store_n = store_counts[did]
        git_n = git_results[did][1] if did in git_results else None
        mark = "ok" if store_n == git_n else "DISAGREE"
        if store_n != git_n:
            all_agree = False
        print(f"#{did}: store={store_n}  git={git_n}  [{mark}]")
    print("-" * 66)
    if all_agree:
        print("All six agree. The field is load-bearing IN THE STORE now, not")
        print("re-derived: --independence answered with no external oracle. The")
        print("flat-markdown -> JSON migration finally closed on this field.")
    else:
        print("MISMATCH. The store thinks a different week than git for some")
        print("essay — a provenance bug --spread was silently absorbing. Name it")
        print("in the essay; do not average the two (seed 175).")
    return store_counts, all_agree


def _corpus_essays():
    """ONE git-backed pass: the corpus's real essays as git knows them today.
    writings/NNN-*.md, tracked, non-seed. This is the single act of leaving home
    that --staleness is allowed. Returns {num: filename}."""
    import subprocess, re
    root = HERE.parent.parent
    try:
        out = subprocess.run(
            ["git", "ls-files", "writings/"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        lines = out.stdout.splitlines()
    except Exception:
        lines = [str(p.relative_to(root)) for p in (root / "writings").glob("*.md")]
    corpus = {}
    for line in lines:
        name = line.split("/")[-1]
        m = re.match(r"^(\d{3})-(.+)\.md$", name)
        if not m:
            continue
        num, rest = int(m.group(1)), m.group(2)
        if rest.startswith("seed") or "-seed-" in name:
            continue
        corpus.setdefault(num, name)
    return corpus


def cmd_staleness(store):
    """177's task: the one census question the store provably cannot answer from
    home -- am I stale? The store knows every essay it recorded as of the last
    persist_weeks.py run. It has no way, from the inside, to learn whether the
    corpus has grown past that snapshot. Currency is not a stored field: the
    instant you write `fresh=true` onto a disposition it begins lying, because
    the next essay written invalidates it and the flag won't know (the exact
    self-certifying move the 164->176 arc kept killing). So staleness stays a
    READ against git, owned by no field.

    STORE-ONLY: the union of every essay the store holds (evidence_weeks keys,
    falling back to evidence lists) plus meta.censused_front.
    ONE git-backed pass: _corpus_essays() enumerates the real corpus.
    Reports the set difference -- essays present in the corpus but absent from
    the store.

    It does NOT claim the missing essays CITE any disposition. That is a session
    judgment, and accrual.py (2026-07-27) proved a lexical mechanic that decides
    citation is a false-positive hazard. --staleness flags the un-metabolized
    corpus as CANDIDATES for judgment; it never files evidence and writes no
    freshness verdict back onto the store."""
    # STORE-ONLY read: what the store believes it holds.
    captured = set()
    for d in store["dispositions"]:
        keys = d.get("evidence_weeks")
        if keys:
            captured |= {int(k) for k in keys}
        else:
            captured |= set(d.get("evidence", []))
    front = store.get("meta", {}).get("censused_front")

    print("STALENESS -- can the store know its snapshot is still the whole story?")
    print("=" * 66)
    print("Store-only: essays the store holds.  One git pass: the corpus today.")
    print("Freshness is never a stored field -- it is this live diff or nothing.")
    print("-" * 66)
    print(f"store holds {len(captured)} distinct essays; highest = {max(captured)}")
    print(f"meta.censused_front = {front}  (the front the store CLAIMS to have read)")

    # THE ONE git-backed pass.
    corpus = _corpus_essays()
    corpus_nums = set(corpus)
    print(f"corpus today (git ls-files) = {len(corpus_nums)} essays; "
          f"highest = {max(corpus_nums) if corpus_nums else None}")
    print("-" * 66)

    missing = sorted(corpus_nums - captured)
    past_front = [n for n in missing if front is not None and n > front]
    if not missing:
        print("EMPTY difference. Every corpus essay is already in the store.")
        print("But note what this cost: the store could not assert it. It took a")
        print("git pass to prove currency. Currency is a live comparison against")
        print("the oracle, not a property the snapshot can self-certify.")
        return {"missing": [], "stale": False, "front": front}

    print(f"NON-EMPTY difference: {len(missing)} corpus essays absent from the store.")
    print(f"missing = {missing}")
    if front is not None:
        print(f"of those, {len(past_front)} were written PAST censused_front={front}: "
              f"{past_front}")
    # Name the sharpest case: the essay that celebrated the store, if it's in the gap.
    for marker in (176,):
        if marker in missing:
            print(f"  -> essay {marker} is in the gap: the essay that celebrated the")
            print(f"     store's independence was itself un-metabolized when it shipped.")
    print("-" * 66)
    print("The store has been stale since it was last written. These essays are")
    print("CANDIDATES for judgment, not auto-filed evidence (accrual.py's lesson).")
    print("The mechanic's honest job: bound what the machine may not decide.")
    return {"missing": missing, "past_front": past_front, "stale": True, "front": front}


def _overlap(a_terms, b_terms):
    """accrual.py's content-term overlap: shared / smaller set."""
    if not a_terms or not b_terms:
        return 0.0
    return len(a_terms & b_terms) / min(len(a_terms), len(b_terms))


def cmd_metabolize(store, bar):
    """178's closing question, made executable: now that --staleness can SEE the
    essays written past the front the store claims to have read, which of them
    can the mechanic even PROPOSE as reinforcement -- and which are invisible to
    it, leaving the judgment entirely to a session?

    This is the join of the two tools the arc already built:
      --staleness  bounds the candidate set (essays past censused_front, absent
                   from the store) -- the ONE git pass this command is allowed.
      accrual.py   supplies the mechanical proposal (census.extract_candidates +
                   content-term overlap against each disposition).

    It writes NOTHING. accrual.py proved a lexical mechanic that DECIDES citation
    is a false-positive hazard; --staleness proved currency is never a stored
    field. So this command's only honest output is a partition of the stale set:
      PROPOSED  -- a delta sentence clears the overlap bar (a floor, not a verdict)
      SEEN-ONLY -- the extractor surfaced a dispositional sentence but nothing
                   cleared the bar (mechanic sees it, cannot match it)
      INVISIBLE -- the extractor surfaced NO candidate sentence at all; whatever
                   these essays reinforce, only judgment can file it.
    The point it measures: how much of the real reinforcement lives in INVISIBLE,
    i.e. below the mechanic entirely -- accrual's automate/escalate asymmetry,
    now scoped to exactly the un-metabolized frontier."""
    import census as C
    import provenance as P

    # --- store-only read: what the store believes it holds (mirror of staleness) ---
    captured = set()
    for d in store["dispositions"]:
        keys = d.get("evidence_weeks")
        captured |= {int(k) for k in keys} if keys else set(d.get("evidence", []))
    front = store.get("meta", {}).get("censused_front")

    # --- the ONE git pass ---
    corpus = _corpus_essays()
    stale = sorted(n for n in corpus if n not in captured and (front is None or n > front))

    disp_terms = {d["id"]: set(P.content_terms(d["text"])) for d in store["dispositions"]}
    cands = [c for c in C.extract_candidates(limit=None) if c["essay"] in set(stale)]
    by_essay = defaultdict(list)
    for c in cands:
        by_essay[c["essay"]].append(c["text"])

    print("METABOLIZE -- of the stale frontier, what can the mechanic even propose?")
    print("=" * 70)
    print(f"censused_front = {front}; stale frontier (past-front, un-stored) = {stale}")
    print(f"overlap bar = {bar}   (accrual.py's floor; a proposal, never a verdict)")
    print("-" * 70)

    proposed, seen_only, invisible = [], [], []
    for essay in stale:
        sents = by_essay.get(essay, [])
        if not sents:
            invisible.append(essay)
            continue
        best_id, best_score, best_text = None, 0.0, ""
        for t in sents:
            ct = set(P.content_terms(t))
            for did, dt in disp_terms.items():
                s = _overlap(ct, dt)
                if s > best_score:
                    best_id, best_score, best_text = did, s, t
        if best_score >= bar:
            proposed.append((essay, best_id, round(best_score, 2), best_text))
        else:
            seen_only.append((essay, best_id, round(best_score, 2), best_text))

    print(f"PROPOSED  (a delta sentence clears the bar): {len(proposed)}")
    for essay, did, score, text in proposed:
        print(f"  essay {essay} -> #{did}  (overlap {score})")
        print(f"      {text[:100]}")
    print(f"\nSEEN-ONLY (extractor found a sentence, nothing matched): {len(seen_only)}")
    for essay, did, score, text in seen_only:
        print(f"  essay {essay} (best #{did} @ {score}): {text[:90]}")
    print(f"\nINVISIBLE (extractor surfaced NO dispositional sentence): {len(invisible)}")
    print(f"  {invisible}")
    print("-" * 70)
    n = len(stale) or 1
    print(f"Mechanic reaches {len(proposed)}/{len(stale)} of the stale frontier as a "
          f"proposal;")
    print(f"{len(invisible)}/{len(stale)} are INVISIBLE to it -- reinforcement there, if any,")
    print("is a session judgment the tool must not pretend to make. This command")
    print("bounds what the machine may decide; it files no evidence and writes no field.")
    return {"stale": stale, "proposed": proposed,
            "seen_only": seen_only, "invisible": invisible}


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
    ap.add_argument("--spread", action="store_true", help="ISO-week span + distinct-week count per disposition (git-backed)")
    ap.add_argument("--independence", action="store_true", help="distinct write-weeks read from the store (zero git) + cross-check vs --spread")
    ap.add_argument("--staleness", action="store_true", help="store-only captured set vs one git pass of the corpus: essays the store never metabolized")
    ap.add_argument("--metabolize", action="store_true", help="partition the stale frontier by what the mechanic can propose vs what only judgment can file")
    ap.add_argument("--bar", type=float, default=0.18, help="overlap bar for --metabolize proposals (accrual.py's floor)")
    ap.add_argument("--json", action="store_true", help="machine-readable graph")
    args = ap.parse_args()

    store = load_store()
    if args.essay is not None:
        cmd_essay(store, args.essay)
    elif args.drop:
        cmd_drop(store, args.drop)
    elif args.dates:
        cmd_dates(store)
    elif args.spread:
        cmd_spread(store)
    elif args.independence:
        cmd_independence(store)
    elif args.staleness:
        cmd_staleness(store)
    elif args.metabolize:
        cmd_metabolize(store, args.bar)
    elif args.overlap:
        cmd_overlap(store)
    elif args.json:
        cmd_json(store)
    else:
        cmd_report(store)


if __name__ == "__main__":
    main()
