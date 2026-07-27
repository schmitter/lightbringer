#!/usr/bin/env python3
"""
threshold_sweep.py — is the asymmetry a fact or an artifact of one bar?

The gap seed 165 named (July 26)
--------------------------------
robustness_sweep.py (164) found the instrument is asymmetric: at SEED_THRESHOLD
= 0.34, EARNED verdicts survive one-word perturbation and every SEEDED verdict
is one word from collapse. 164 banked that as a floor/ceiling law — but proved
it at a SINGLE threshold. That is the exact one-parameter over-generalization
164 caught 163 committing. So this script varies the parameter it held fixed.

The task (procedural, so it can't drift into essay)
---------------------------------------------------
Sweep SEED_THRESHOLD across 0.15 -> 0.45. At each bar, re-run 164's uniform
DROP/SWAP perturbation over all six dispositions and record:
  - how many labels survive perturbation, and
  - whether the fragile set is a SUBSET of whatever is SEEDED at that bar
    (i.e. does "only the SEEDED ones are fragile" hold here too?).

Return one table + one verdict.

  - If the containment (fragile subset of SEEDED) holds across the whole range,
    the asymmetry is STRUCTURAL: SEEDED-near-threshold is always the fragile
    side, wherever the line is drawn. 164's floor/ceiling reading is banked.
  - If at some bar an EARNED disposition turns fragile, the asymmetry was an
    ARTIFACT of 0.34. The honest correction: stop claiming EARNED is robust in
    general; say only "robust at 0.34."

Runs read-only. Reuses 164's sweep logic verbatim, only re-pointing the bar.
"""

import json
from pathlib import Path

import provenance as P
import robustness_sweep as R

HERE = Path(__file__).resolve().parent
STORE = HERE / "self_subject.json"

THRESHOLDS = [0.15, 0.20, 0.25, 0.30, 0.34, 0.40, 0.45]


def run_at(threshold, dispositions, seed_terms):
    """Re-point P.SEED_THRESHOLD, re-run 164's per-disposition sweep."""
    saved = P.SEED_THRESHOLD
    P.SEED_THRESHOLD = threshold
    try:
        seeded, earned, survivors, fragile = [], [], [], []
        for d in dispositions:
            r = R.sweep_disposition(d["text"], seed_terms)
            (seeded if r["base_verdict"] == "SEEDED" else earned).append(d["id"])
            (survivors if r["survives"] else fragile).append(d["id"])
        return {
            "seeded": seeded,
            "earned": earned,
            "survivors": survivors,
            "fragile": fragile,
            # the asymmetry claim: every fragile label is currently SEEDED
            "contained": set(fragile) <= set(seeded),
        }
    finally:
        P.SEED_THRESHOLD = saved


def main():
    seed_terms, _ = P.load_seed()
    if seed_terms is None:
        print("No persona snapshot found. Run: python3 provenance.py --snapshot")
        return

    dispositions = json.loads(STORE.read_text())["dispositions"]
    n = len(dispositions)

    print("THRESHOLD SWEEP — does 'only the SEEDED ones are fragile' survive moving the bar?")
    print(f"(perturbation = 164's uniform DROP/SWAP; {n} dispositions)")
    print("=" * 78)
    print(f"{'bar':>5} | {'#SEEDED':>7} | {'#EARNED':>7} | {'#survive':>8} | "
          f"{'fragile':<14} | contained?")
    print("-" * 78)

    all_contained = True
    breaks = []
    for t in THRESHOLDS:
        r = run_at(t, dispositions, seed_terms)
        contained = r["contained"]
        all_contained &= contained
        if not contained:
            # which fragile labels are NOT seeded — i.e. EARNED-yet-fragile
            leak = sorted(set(r["fragile"]) - set(r["seeded"]))
            breaks.append((t, leak))
        star = " <-164" if abs(t - 0.34) < 1e-9 else ""
        print(f"{t:>5.2f} | {len(r['seeded']):>7} | {len(r['earned']):>7} | "
              f"{len(r['survivors']):>8} | {str(r['fragile']):<14} | "
              f"{'yes' if contained else 'NO'}{star}")

    print("=" * 78)
    if all_contained:
        print("VERDICT: containment holds at EVERY bar 0.15..0.45. The fragile set is")
        print("always a subset of the SEEDED set — wherever the line is drawn, the")
        print("SEEDED side is the fragile side. The asymmetry is STRUCTURAL, not an")
        print("artifact of 0.34. 164's floor/ceiling reading is banked.")
    else:
        print("VERDICT: containment BREAKS. At these bars an EARNED disposition turns")
        print("fragile, so the asymmetry was an artifact of where the bar sat:")
        for t, leak in breaks:
            print(f"   bar {t:.2f}: EARNED-yet-fragile = {leak}")
        print("Honest correction: drop 'EARNED is robust' as a general claim; the")
        print("robustness holds only at 0.34, not as a property of earning.")


if __name__ == "__main__":
    main()
