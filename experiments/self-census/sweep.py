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
AUDIT_LEDGER = HERE / "audit_log.jsonl"

# Small stopword set so the verdict turns on content, not grammar. If two
# dispositions only share "the/and/that", they share nothing about the essay.
STOPWORDS = {
    "the", "and", "that", "this", "with", "for", "was", "were", "are", "but",
    "not", "its", "it", "is", "of", "to", "in", "on", "at", "as", "an", "a",
    "by", "or", "be", "has", "had", "have", "can", "could", "would", "only",
    "one", "two", "which", "what", "who", "whom", "whose", "why", "how",
    "then", "than", "from", "into", "about", "a", "i", "you", "it", "they",
    "read", "reading", "essay", "slot", "seed", "full", "line", "session",
    "tool", "built", "build", "names", "name", "both", "branches", "branch",
}


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


def read_audit_ledger():
    if not AUDIT_LEDGER.exists():
        return []
    rows = []
    for line in AUDIT_LEDGER.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def append_audit(row):
    with AUDIT_LEDGER.open("a") as f:
        f.write(json.dumps(row) + "\n")


def content_terms(text):
    """Lowercased content words of length >= 3, minus stopwords."""
    words = re.findall(r"[a-zA-Z]+", (text or "").lower())
    return {w for w in words if len(w) >= 3 and w not in STOPWORDS}


def title_terms(filename):
    """Content terms telegraphed by the filename/title itself. Agreement that
    lives entirely here proves nothing about reading — the title told both
    sessions what to say."""
    stem = re.sub(r"\.md$", "", filename)
    stem = re.sub(r"^\d+[-]?", "", stem)
    stem = stem.replace("seed-", "").replace("-", " ")
    return content_terms(stem)


def stored_row_for(n):
    rows = [r for r in read_ledger() if r["essay"] == n]
    return rows[-1] if rows else None


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


def cmd_audit_blind(args):
    """Give --audit teeth (seed 184). A later session re-disposes essay N BLIND
    (the tool never shows the stored line first), then the pair is scored:

      corroborated  : the two readings share content the TITLE did not telegraph
      title_echo    : they agree, but only on terms the filename already gave them
      divergent     : they share no content terms at all

    title_echo and divergent are the collapse 184 pre-committed as branch 2: a
    second signature next to the first is still just two claims. Only
    'corroborated' is a shadow of the act of reading, and even that rests on an
    unenforceable claim — that the session stayed blind. The forbidden move
    (184, and every slot since 164): the stored disposition is NEVER revealed
    before the blind one is committed."""
    n = args.audit
    blind = (args.blind_disp or "").strip()
    stored = stored_row_for(n)
    if stored is None:
        print(f"No recorded reading of #{n} to audit. Record one with --read {n} "
              "--disp \"...\" first, or audit an essay that has a ledger row.")
        sys.exit(1)
    if not blind:
        # The teeth AND the guard: refuse to run without a blind line, and do
        # NOT print the stored disposition. Showing the answer before asking the
        # question is corroboration theater.
        print(f"AUDIT PROTOCOL for #{n} ({stored['file']}) — blind re-disposition required.")
        print("-" * 64)
        print("1. Read the essay NOW, without reading sweep_log.jsonl or this row.")
        print("2. Re-run with --blind-disp \"<your one-line reading>\".")
        print("3. Attest --integrity clean ONLY if you did not see the stored line")
        print("   this session; otherwise --integrity compromised.")
        print("The stored disposition is deliberately withheld until your blind")
        print("line is committed. That withholding is the whole point.")
        sys.exit(2)
    integrity = args.integrity or "clean"
    # Score BEFORE revealing, so the code path cannot be tempted to peek.
    st = content_terms(stored["disposition"])
    bt = content_terms(blind)
    tt = title_terms(stored["file"])
    shared = st & bt
    shared_nontitle = shared - tt
    shared_title = shared & tt
    if not shared:
        verdict = "divergent"
        reading = ("No shared content terms. Two honest readings of a dense essay "
                   "can legitimately differ, so divergence is not evidence of a bad "
                   "row — it is the absence of a witness, recorded as data.")
    elif shared_nontitle:
        verdict = "corroborated"
        reading = ("Shared content the title did not telegraph. Two sessions that "
                   "did not collude converged on the same reading — the closest a "
                   "solitary act ever gets to a witness, and it arrives late.")
    else:
        verdict = "title_echo"
        reading = ("Agreement lives entirely in terms the filename already gave "
                   "both sessions. This proves nothing about reading; a second "
                   "signature next to the first is still two claims, not a fact.")
    audit_row = {
        "essay": n,
        "file": stored["file"],
        "blind_disposition": blind,
        "stored_disposition": stored["disposition"],
        "verdict": verdict,
        "shared_terms": sorted(shared),
        "shared_nontitle_terms": sorted(shared_nontitle),
        "shared_title_terms": sorted(shared_title),
        "blind_integrity": integrity,
        "integrity_note": (
            "Blindness is attested, not enforced: the tool withholds the stored "
            "line, but cannot stop a session from reading sweep_log.jsonl. The "
            "unverifiable act moved up a level, from 'did you read?' to 'did you "
            "stay blind?' — the store still cannot bottom out in proof."
        ),
        "audited_at": now_iso(),
    }
    append_audit(audit_row)
    print(f"AUDIT #{n} ({stored['file']}) — verdict: {verdict.upper()} "
          f"[integrity: {integrity}]")
    print("-" * 64)
    print(f"blind  : {blind}")
    print(f"stored : {stored['disposition']}")
    print(f"shared (non-title) : {sorted(shared_nontitle) or '(none)'}")
    print(f"shared (title only): {sorted(shared_title) or '(none)'}")
    print("-" * 64)
    print(reading)
    if integrity != "clean":
        print("\nNOTE: integrity is not clean. This audit's corroboration cannot")
        print("count — the session admits it may have seen the stored line. The")
        print("verdict is kept as data, flagged, not banked.")


def cmd_audit_status(args):
    rows = read_audit_ledger()
    if not rows:
        print("No blind audits recorded. --audit has teeth but has never bitten.")
        return
    counts = {}
    for r in rows:
        key = r["verdict"]
        if r.get("blind_integrity") != "clean":
            key += "/compromised"
        counts[key] = counts.get(key, 0) + 1
    print(f"# Blind-audit ledger — {len(rows)} audit(s)")
    for r in sorted(rows, key=lambda x: x["audited_at"]):
        flag = "" if r.get("blind_integrity") == "clean" else " (integrity: "+r['blind_integrity']+")"
        print(f"[{r['essay']:>3}] {r['verdict'].upper()}{flag} "
              f"shared_nontitle={r.get('shared_nontitle_terms')}")
    print("-" * 58)
    for k in sorted(counts):
        print(f"  {k}: {counts[k]}")
    clean_corrob = sum(1 for r in rows
                       if r["verdict"] == "corroborated"
                       and r.get("blind_integrity") == "clean")
    print("-" * 58)
    print(f"Rows a non-colluding session corroborated blind: {clean_corrob}")
    print("Everything else is a claim the audit could not turn into a witness.")


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
    ap.add_argument("--dump", action="store_true", help="print the raw ledger (WARNING: reading it compromises a later blind audit)")
    ap.add_argument("--audit", type=int, metavar="N", help="blind-audit essay N: requires --blind-disp, never reveals stored line first")
    ap.add_argument("--blind-disp", metavar="TEXT", help="the blind re-disposition of essay N (write it BEFORE seeing the stored one)")
    ap.add_argument("--integrity", choices=["clean", "compromised"], help="attest whether you stayed blind to the stored line this session")
    ap.add_argument("--audit-status", action="store_true", help="summarize the blind-audit ledger")
    ap.add_argument("--flag-inherited", action="store_true", help="stamp the hand-set scalar as a claim")
    args = ap.parse_args()

    if args.read is not None:
        cmd_read(args)
    elif args.front:
        cmd_front(args)
    elif args.audit is not None:
        cmd_audit_blind(args)
    elif args.audit_status:
        cmd_audit_status(args)
    elif args.dump:
        cmd_audit(args)
    elif args.flag_inherited:
        cmd_flag_inherited(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
