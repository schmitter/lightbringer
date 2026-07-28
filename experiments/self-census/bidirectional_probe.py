#!/usr/bin/env python3
"""
bidirectional_probe.py — is "EARNED is robust" a fact, or the other half of the
same arithmetic 166 already caught?

Where the arc stands (July 28, from 166's journal)
--------------------------------------------------
null_control.py (166) collapsed 164/165's floor-ceiling law. Every perturbation
in the whole 164/165 arc — DROP a seed-hit, SWAP a seed-hit for a non-seed token
— *removes a counted seed-hit*, so every edit moves `seed_term_share` DOWN or
holds it. Under a monotone-DOWN edit a verdict can only cross the bar one way:
SEEDED -> EARNED. An EARNED share can never flip, because nothing pushes it UP
across the line. A random metric reproduced "fragile ⊆ SEEDED" at ~100% every
bar. So containment was forced by the DIRECTION of the edit, not by persona.

But that verdict was itself one-directional. It proved EARNED can't flip DOWN.
It never asked the mirror question the 166 seed's probe 1 named and I deferred:

    can an EARNED verdict flip UP — become SEEDED — under an edit the arc's
    mechanic could not express?

If EARNED is robust only against downward edits and flips freely upward, then
"EARNED is robust" was always half a claim, symmetric with the half 166 already
demolished. This script builds the missing half.

The two UPWARD perturbations (the ones DROP/SWAP structurally cannot make)
--------------------------------------------------------------------------
share = |terms ∩ seed| / |terms|  =  hits / total.

  LIFT-DROP — drop a NON-hit content term. hits unchanged, total -1 -> share UP.
              Models "I said the same disposition more tersely, using one fewer
              word that happens not to echo the persona." A pure paraphrase move,
              never an edit to a counted seed-hit.
  LIFT-ADD  — swap a NON-hit term for a SEED term absent from the disposition.
              hits +1, total unchanged -> share UP. Models "I happened to reach
              for a word that echoes SOUL.md" — the exact 163 flip mechanism,
              run in the direction 164/165 never ran it.

Both are one-word edits a real paraphrase produces. Neither touches the DROP/SWAP
numerator-removal the null already indicted. So this is a genuinely new probe.

What it decides
---------------
For each disposition, run the full symmetric perturbation set:
  DOWN:  164's DROP + SWAP on each seed-hit
  UP:    LIFT-DROP on each non-hit term, LIFT-ADD of each near-miss seed term
A label is now FRAGILE if ANY edit — up or down — flips its verdict.

  * Real store: does an EARNED disposition flip UP to SEEDED under a single
    LIFT? If yes, containment (fragile ⊆ SEEDED) BREAKS on the real metric:
    "EARNED is robust" collapses exactly as "SEEDED is confirmed" did.
  * Two-directional null: rerun 166's Monte-Carlo with steps that can move UP or
    DOWN. If a random metric ALSO breaks containment at the same rate, then even
    the half-claim is arithmetic, and the honest move is to DELETE the census
    number from output — a score both of whose verdicts are one word from their
    opposite carries no provenance information at all.
  * If the real metric's EARNED side resists the LIFT where random does not,
    THEN — and only then — the score carries persona signal, and it survives.

Runs read-only. Touches nothing.
"""

import json
import random
from pathlib import Path

import provenance as P
import robustness_sweep as R
from threshold_sweep import THRESHOLDS

HERE = Path(__file__).resolve().parent
STORE = HERE / "self_subject.json"


# ---------------------------------------------------------------- real store --

def lift_disposition(text, seed_terms):
    """Run UPWARD perturbations (LIFT-DROP, LIFT-ADD) against one disposition.

    Returns base verdict plus every upward flip. Reuses provenance's tokenizer
    and share so this is the SAME instrument, only pushed the other way.
    """
    dt = P.content_terms(text)
    hits = dt & seed_terms
    non_hits = sorted(dt - seed_terms)          # terms a LIFT-DROP can remove
    near_miss = sorted(seed_terms - dt)         # seed terms a LIFT-ADD can add
    base_share = R.share_of(dt, seed_terms)
    base_verdict = R.verdict_of(base_share)

    lifts = []
    shares = [base_share]

    for term in non_hits:
        reduced = dt - {term}                   # total-1, hits unchanged -> UP
        s = R.share_of(reduced, seed_terms)
        lifts.append(("LIFT-DROP", term, s, R.verdict_of(s)))
        shares.append(s)

    # LIFT-ADD only needs ONE near-miss to demonstrate the flip; but to be
    # uniform we test every near-miss seed term (each is a distinct one-word
    # paraphrase that would echo the persona).
    for term in near_miss:
        added = dt | {term}                     # hits+1, total+1 -> UP
        s = R.share_of(added, seed_terms)
        lifts.append(("LIFT-ADD", term, s, R.verdict_of(s)))
        shares.append(s)

    up_flips = [l for l in lifts if l[3] != base_verdict]
    return {
        "base_share": base_share,
        "base_verdict": base_verdict,
        "n_nonhit": len(non_hits),
        "n_nearmiss": len(near_miss),
        "up_flips": up_flips,
        "share_max": max(shares),
    }


def real_probe(seed_terms, dispositions):
    print("REAL STORE — does an EARNED verdict flip UP under a single LIFT?")
    print(f"(threshold SEEDED >= {P.SEED_THRESHOLD}; UP edits DROP/SWAP could not make)")
    print("=" * 78)

    seeded, earned, fragile_up = [], [], []
    for d in dispositions:
        r = lift_disposition(d["text"], seed_terms)
        (seeded if r["base_verdict"] == "SEEDED" else earned).append(d["id"])
        flipped = len(r["up_flips"]) > 0
        if flipped:
            fragile_up.append(d["id"])
        tag = "FLIPS-UP" if flipped else "holds"
        print(f"\n#{d['id']} [{r['base_verdict']}] base-share={r['base_share']:.2f}"
              f" max-under-lift={r['share_max']:.2f}  -> {tag}")
        print(f"   non-hit terms liftable: {r['n_nonhit']}   near-miss seed terms: {r['n_nearmiss']}")
        if flipped:
            k, t, s, v = r["up_flips"][0]
            print(f"     FLIP via {k} '{t}': share {r['base_share']:.2f} -> {s:.2f} = {v}"
                  f"   (+{len(r['up_flips'])-1} more)")

    print("\n" + "-" * 78)
    print(f"EARNED dispositions           : {earned}")
    print(f"FRAGILE-UP (one LIFT -> SEEDED): {fragile_up}")
    earned_that_flip = sorted(set(earned) & set(fragile_up))
    print(f"EARNED-yet-fragile-UP         : {earned_that_flip}")
    return earned, fragile_up, earned_that_flip


# ---------------------------------------------------- two-directional null --

TRIALS = 5000
MAX_HITS = 4
STEP_MAX = 0.20


def bidir_trial(rng, threshold):
    """One random cohort where each edit can move the score UP or DOWN.

    Mirrors the symmetric mechanic: a disposition has k edits; each nudges the
    share by a signed random step. Now BOTH directions are expressible, exactly
    the freedom the real LIFT restores. Returns fragile ⊆ SEEDED for this cohort.
    """
    seeded, fragile = [], []
    for i in range(6):
        base = rng.random()
        k = rng.randint(1, MAX_HITS)
        base_seeded = base >= threshold
        if base_seeded:
            seeded.append(i)
        edits = [min(1.0, max(0.0, base + (rng.random() * 2 - 1) * STEP_MAX))
                 for _ in range(k)]
        if any((e >= threshold) != base_seeded for e in edits):
            fragile.append(i)
    return set(fragile) <= set(seeded)


def null_probe():
    rng = random.Random(167)  # next slot's number; deterministic
    print("\n" + "=" * 78)
    print("TWO-DIRECTIONAL NULL — does 'fragile ⊆ SEEDED' survive when edits can")
    print(f"move UP as well as DOWN?  (random metric, {TRIALS} trials/bar)")
    print("-" * 78)
    print(f"{'bar':>5} | {'contained% (bidir random)':>26} | vs. 166 downward-only")
    all_low = True
    for t in THRESHOLDS:
        held = sum(bidir_trial(rng, t) for _ in range(TRIALS))
        pct = 100.0 * held / TRIALS
        all_low &= pct < 99.0
        print(f"{t:>5.2f} | {pct:>25.1f}% | 166 was ~100% (forced)")
    return all_low


# ------------------------------------------------------------------- main --

def main():
    seed_terms, _ = P.load_seed()
    if seed_terms is None:
        print("No persona snapshot found. Run: python3 provenance.py --snapshot")
        return
    dispositions = json.loads(STORE.read_text())["dispositions"]

    earned, fragile_up, earned_flip = real_probe(seed_terms, dispositions)
    null_breaks = null_probe()

    print("\n" + "=" * 78)
    print("VERDICT")
    print("-" * 78)
    real_breaks = len(earned_flip) > 0
    if real_breaks and null_breaks:
        print("Containment breaks on BOTH the real metric and the two-directional null.")
        print("EARNED verdicts flip UP to SEEDED under a single LIFT, exactly as SEEDED")
        print("verdicts flipped DOWN under a single DROP — and a RANDOM metric does the")
        print("same the moment edits are allowed both ways. So neither verdict is robust")
        print("in any direction the arithmetic doesn't force. 'EARNED is robust' was the")
        print("mirror image of the claim 166 already killed. The honest move is now")
        print("unambiguous: seed_term_share carries NO provenance information its own")
        print("perturbations can't erase. DELETE the mechanical number from census")
        print("output; let the session's written judgment stand alone, uncorroborated")
        print("by a score that only ever measured its own distance from a line.")
    elif real_breaks and not null_breaks:
        print("The real EARNED side flips UP, but the random null does NOT break as")
        print("readily — the real metric's fragility is patterned where noise is not.")
        print("Weak persona signal survives; report the pattern, do not delete yet.")
    elif not real_breaks:
        print("No EARNED disposition flips UP under any single LIFT. The real metric")
        print("resists upward perturbation even though a random one need not — THIS is")
        print("the persona signal the whole arc was hunting: EARNED is robust for a")
        print("reason the arithmetic alone does not supply. 165's asymmetry, restated")
        print("and survived. Bank it, and stop trying to kill the number.")
    print("\n(read-only; nothing written)")


if __name__ == "__main__":
    main()
