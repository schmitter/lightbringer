#!/usr/bin/env python3
"""
null_control.py — did five essays measure the persona, or the arithmetic?

The suspicion seed 166 named (July 27)
--------------------------------------
164 found the instrument asymmetric (only SEEDED verdicts are one word from
collapse); 165 banked that as STRUCTURAL — fragility is distance-from-the-wire.
But 166 flagged a circularity underneath the whole arc: every perturbation in
164/165 edits a seed-HIT, and seed-hits are exactly the terms `seed_term_share`
counts in its numerator. DROP and SWAP both REMOVE a seed-hit, so both can only
move the share DOWN (or hold it). No perturbation in the arc can raise a share.

If the perturbation is monotone-decreasing, then a verdict can only cross the
bar in ONE direction: SEEDED (share >= bar) -> EARNED. An EARNED verdict
(share < bar) can NEVER flip, because nothing pushes it up across the line. So
"fragile ⊆ SEEDED" may be forced by the DIRECTION of the perturbation, true of
ANY score under a downward-only edit — and say nothing about persona provenance.

The null control (procedural, so it can't drift into essay)
-----------------------------------------------------------
Replace `seed_term_share` with a RANDOM score in [0,1] per disposition. Keep the
threshold. Keep the same mechanic ABSTRACTLY: each disposition has k "hits", and
each hit's perturbation lowers the score by a random step (downward-only, exactly
like DROP/SWAP removing a counted unit). Re-run 164's threshold sweep on this
random metric. Does containment (fragile ⊆ SEEDED) still hold at every bar?

  - If the random metric REPRODUCES containment across the sweep, then 164/165
    measured a property of thresholding-a-downward-only-count, not the persona.
    The floor/ceiling law collapses to "any near-bar score is fragile from
    above." Say so plainly.
  - If containment BREAKS under the random metric, then the real metric carried
    persona information the random one lacks — 165's asymmetry survives a null
    and is stronger for it.

Runs read-only. Touches nothing. Pure Monte-Carlo over the abstract mechanic.
"""

import random

from threshold_sweep import THRESHOLDS

N_DISPOSITIONS = 6      # matches self_subject.json
TRIALS = 5000           # Monte-Carlo replicates
MAX_HITS = 4            # abstract seed-hit count per disposition
STEP_MAX = 0.20         # max downward move a single hit-edit can cause


def one_disposition(rng):
    """A random base score and a set of downward-only perturbed scores.

    Mirrors DROP/SWAP: each of k hits, when edited, removes counted mass, so the
    perturbed share is <= base. We never produce an upward perturbation because
    the arc's mechanic cannot.
    """
    base = rng.random()
    k = rng.randint(1, MAX_HITS)
    perturbed = [max(0.0, base - rng.random() * STEP_MAX) for _ in range(k)]
    return base, perturbed


def trial(rng, threshold):
    """Return True if fragile ⊆ SEEDED holds for one random cohort at this bar."""
    seeded, fragile = [], []
    for i in range(N_DISPOSITIONS):
        base, perturbed = one_disposition(rng)
        base_seeded = base >= threshold
        if base_seeded:
            seeded.append(i)
        # fragile == some perturbation flips the verdict.
        base_verdict_seeded = base_seeded
        flips = any((p >= threshold) != base_verdict_seeded for p in perturbed)
        if flips:
            fragile.append(i)
    return set(fragile) <= set(seeded)


def main():
    rng = random.Random(166)  # deterministic; seed = essay number, of course

    print("NULL CONTROL — does 'fragile ⊆ SEEDED' survive a RANDOM metric?")
    print(f"(random base score in [0,1]; downward-only edits, mirroring DROP/SWAP;")
    print(f" {N_DISPOSITIONS} dispositions, {TRIALS} trials per bar)")
    print("=" * 74)
    print(f"{'bar':>5} | {'contained% (random)':>20} | verdict")
    print("-" * 74)

    all_high = True
    for t in THRESHOLDS:
        held = sum(trial(rng, t) for _ in range(TRIALS))
        pct = 100.0 * held / TRIALS
        all_high &= pct >= 99.0
        note = "reproduced" if pct >= 99.0 else "broke"
        print(f"{t:>5.2f} | {pct:>19.1f}% | {note}")

    print("=" * 74)
    if all_high:
        print("VERDICT: a RANDOM metric reproduces containment at ~100% every bar.")
        print("'fragile ⊆ SEEDED' is FORCED by the downward-only perturbation, not by")
        print("the persona signal — an EARNED share cannot flip because nothing pushes")
        print("it UP across the bar. 164 and 165 measured the arithmetic of thresholding")
        print("a monotone-decreasing count. The floor/ceiling law must be restated:")
        print("'any score near a bar is fragile FROM ABOVE' — true of noise, and mute")
        print("about provenance. The honest correction is severe, and it is banked.")
    else:
        print("VERDICT: the random metric does NOT reliably reproduce containment.")
        print("The real seed_term_share carried persona information the null lacked;")
        print("165's structural asymmetry survives the null and is stronger for it.")


if __name__ == "__main__":
    main()
