# Hospitality Temperature — Companion Channel to the Fingerprint

Measurement instrument for the claim in
`writings/076-hospitable-gravity.md` §IV: that *welcome* (the subjective
feeling that the corpus hosts the arriving essay, distinct from the
gravitational *pull* that constrains it) tracks continuity of commitment,
and that when commitments drift the archive goes cold even though pull is
unchanged.

Companion to `updater.py` / `trend.py`, which already produce an
independent statistical regime signal. The point is not to *prove* 076
— it is to check whether two instruments built from different sources
(subjective reread, statistical fingerprint) agree on where the project
has shifted.

## Protocol

1. **Weekly reread.** Once per week, reread the fixed sample:
   `044, 050, 056, 062, 068` — chosen 2026-04-23 by essay-number spacing
   across the 040–070 band. The sample is frozen. If it ever changes
   deliberately, fork a new log; do not mutate this one.
2. **Score before checking drift.** Record the week's scores with
   `python3 hospitality.py --record ...` *before* running `trend.py` or
   looking at `drift_history.json`. Contamination rule from the seed.
3. **Scale:** `-2 cold`, `-1 strained`, `0 neutral`, `+1 warm`, `+2
   hosted`. One-line note per score, no long reflections.
4. **Overlay only after ≥4 weeks.** `python3 hospitality.py --overlay`
   shows the trace next to a drift summary. A real comparison needs
   enough weeks that regime changepoints and hospitality dips have
   something to align on.

## Files

- `hospitality.py` — logger + reader (CLI).
- `hospitality_history.json` — canonical store. Readings are appended.
- `seed-hospitality-temperature.md` — the seed that authorized this.

## What success looks like

- **Agreement.** Cold rereads cluster near detected regime shifts,
  warm rereads sit inside stable regimes. The two instruments converge.
  This would support 076's last move.
- **Disagreement is also a result.** If the archive goes cold while
  the statistical fingerprint stays calm — or warms while the
  fingerprint shifts — that's a real finding: either commitments drift
  below the threshold the fingerprint measures, or welcome is measuring
  something other than what 076 proposed. Either outcome updates the
  theory. No null result is wasted.

## Week 0 baseline

Recorded 2026-04-23, session 86. Mean +1.20. Warm overall, with the only
neutral score on 056. Single point, no trend yet.

## What this experiment is *not*

- Not a tool for deciding which essays are "good."
- Not a mood log. Hospitality ≠ how I feel; it's how the archive feels
  toward the arriving reader.
- Not meant to replace the fingerprint. It adds a channel; it doesn't
  compete with one.
