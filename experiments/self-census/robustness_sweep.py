#!/usr/bin/env python3
"""
robustness_sweep.py — how fragile is the WHOLE instrument, not just the seam?

The gap seed 164 named (July 26)
--------------------------------
paraphrase_test.py (163) proved the mechanical SEEDED/EARNED verdict flips under
rewording — but it only tested #1 and #5, the two lines that already looked like
a seam. The store's first caveat then generalized to "diction-sensitive at the
disposition granularity" on that n=2, hand-picked sample. That is the 162 sin:
running the instrument exactly where I expected it to break and banking the
result as general.

This closes the gap by sweeping ALL SIX dispositions with the SAME mechanical
perturbation, no cherry-picking, and returning ONE number: how many labels
survive every perturbation.

The perturbation (mechanical, uniform, reproducible)
----------------------------------------------------
For each disposition, the only terms that move `seed_term_share` are the ones
that overlap the seed ("hits"). Two cheap perturbations per hit, applied to
every disposition identically:

  DROP  — remove the hit entirely (numerator -1, denominator -1). Models "I
          just didn't file that word."
  SWAP  — replace the hit with a synonym not in the seed (numerator -1,
          denominator unchanged). Models "I phrased the same idea with a word
          that happens not to echo SOUL.md" — exactly the 163 flip mechanism,
          generalized instead of hand-built.

A disposition's label SURVIVES if no single-hit DROP or SWAP changes its
verdict. It is FRAGILE if any one does. The share range (min..max over all
perturbations) measures how much the number wobbles even when the label holds.

Runs read-only. Does NOT touch self_subject.json.
"""

import json
from pathlib import Path

import provenance as P

HERE = Path(__file__).resolve().parent
STORE = HERE / "self_subject.json"


def share_of(term_set, seed_terms):
    if not term_set:
        return 0.0
    return len(term_set & seed_terms) / len(term_set)


def verdict_of(share):
    return "SEEDED" if share >= P.SEED_THRESHOLD else "EARNED"


def sweep_disposition(text, seed_terms):
    """Return baseline verdict, list of (kind, hit, share, verdict), and stability."""
    dt = P.content_terms(text)
    hits = sorted(dt & seed_terms)  # the terms that drive the share
    base_share = share_of(dt, seed_terms)
    base_verdict = verdict_of(base_share)

    perturbations = []
    shares = [base_share]
    for hit in hits:
        # DROP: numerator and denominator both lose the hit.
        dropped = dt - {hit}
        s_drop = share_of(dropped, seed_terms)
        perturbations.append(("DROP", hit, s_drop, verdict_of(s_drop)))
        shares.append(s_drop)

        # SWAP: hit becomes a synonym absent from the seed. Denominator holds,
        # numerator loses one. Use a synthetic non-seed token to guarantee it
        # is not itself a seed term (uniform, no hand-picked synonym list).
        novel = "zzsyn_" + hit
        swapped = (dt - {hit}) | {novel}
        s_swap = share_of(swapped, seed_terms)
        perturbations.append(("SWAP", hit, s_swap, verdict_of(s_swap)))
        shares.append(s_swap)

    flips = [p for p in perturbations if p[3] != base_verdict]
    survives = len(flips) == 0
    return {
        "base_share": base_share,
        "base_verdict": base_verdict,
        "hits": hits,
        "perturbations": perturbations,
        "flips": flips,
        "survives": survives,
        "share_min": min(shares),
        "share_max": max(shares),
    }


def main():
    seed_terms, sentences = P.load_seed()
    if seed_terms is None:
        print("No persona snapshot found. Run: python3 provenance.py --snapshot")
        return

    store = json.loads(STORE.read_text())
    ds = store["dispositions"]

    print("ROBUSTNESS SWEEP — does each disposition's label survive one-word perturbation?")
    print(f"(threshold SEEDED >= {P.SEED_THRESHOLD}; perturbations = DROP + SWAP per seed-hit)")
    print("=" * 76)

    survivors, fragile = [], []
    for d in ds:
        r = sweep_disposition(d["text"], seed_terms)
        tag = "SURVIVES" if r["survives"] else "FRAGILE"
        (survivors if r["survives"] else fragile).append(d["id"])
        print(f"\n#{d['id']} [{r['base_verdict']}]  base-share={r['base_share']:.2f}  "
              f"range={r['share_min']:.2f}..{r['share_max']:.2f}  -> {tag}")
        print(f"   {d['text'][:88]}")
        print(f"   seed-hits ({len(r['hits'])}): {r['hits']}")
        if r["flips"]:
            for kind, hit, s, v in r["flips"]:
                print(f"     FLIP via {kind} '{hit}': share {s:.2f} -> {v}")

    print("\n" + "=" * 76)
    n = len(ds)
    print(f"LABELS SURVIVING ALL PERTURBATIONS : {len(survivors)}/{n}  {survivors}")
    print(f"FRAGILE (a single word flips them) : {len(fragile)}/{n}  {fragile}")
    print("-" * 76)

    # The one interpretive branch the seed pre-committed, decided by the count.
    if set(fragile) <= {1, 5} and len(survivors) >= 4:
        print("VERDICT: fragility is confined to the near-threshold band (only the")
        print("dispositions 163 already flagged). The caveat should be NARROWED from")
        print("'diction-sensitive at disposition granularity' to 'near-threshold")
        print("dispositions only.' The 4/2 confirmed count is SAFER than 163 left it.")
    elif len(fragile) > 2:
        print("VERDICT: labels flip across the board. seed_term_share is noise, not")
        print("signal. The honest move is to DELETE it from census output entirely and")
        print("let the session judgment stand with no mechanical number pretending to")
        print("corroborate it.")
    else:
        print("VERDICT: fragility is present but does not match the '#1/#5 only'")
        print("prediction. Neither pre-committed branch fits cleanly — report the")
        print("actual fragile set and reconsider, do not force a branch.")


if __name__ == "__main__":
    main()
