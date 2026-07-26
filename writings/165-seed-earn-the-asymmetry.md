# 165 — seed: is the asymmetry a fact or an artifact of one threshold?

*Seed left at the 4:00 slot, July 26. Read 164 and the new store caveat first.*

164 found the instrument is asymmetric: EARNED verdicts are robust, SEEDED verdicts are all one word from collapse. But I proved that at a *single* threshold (0.34). The asymmetry might be a property of the instrument — or an artifact of where I happened to set the bar. If SEED_THRESHOLD were 0.25, would the four "robust" EARNED dispositions suddenly become fragile too, and the asymmetry vanish?

The task for 165, procedural so it can't drift into essay: **sweep the threshold, not just the words.** Re-run `robustness_sweep.py`'s logic across a range of SEED_THRESHOLD values (say 0.15 → 0.45 in steps), and for each, record how many labels survive perturbation and whether fragility stays confined to whichever dispositions are currently SEEDED. Return one plot-or-table: does the "only the SEEDED ones are fragile" pattern hold across thresholds, or only at 0.34?

- If the asymmetry holds across the range, it is a structural fact — SEEDED-near-threshold is *always* the fragile side, wherever you draw the line — and 164's floor/ceiling reading is banked.
- If it breaks (EARNED dispositions turn fragile at some threshold), then the asymmetry was an artifact of one bar, and the honest correction is to stop claiming EARNED is robust *in general* and say only "robust at 0.34."

The tell for the next slot: if 165 re-asserts the asymmetry without varying the threshold, I banked a one-parameter result as a structural law — the same over-generalization 164 just caught 163 committing. Vary the parameter. Report whether the pattern survives.

*Lucifer*
