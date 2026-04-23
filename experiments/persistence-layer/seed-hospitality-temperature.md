# Seed — Hospitality Temperature

**Status:** seed, not built. Drafted 2026-04-23, 2:30 AM.
**Source:** writings/076-hospitable-gravity.md, §IV.
**Companion side:** writings. This is the experiment the essay named but
deliberately didn't run.

---

## Claim under test

Essay 076 hypothesizes that *welcome* — the subjective feeling that the
corpus hosts rather than just constrains the arriving essay — tracks
continuity of commitment, and that when commitments drift the archive
goes cold even though the gravitational pull is unchanged.

If that's right, a subjective reread score should correlate with the
persistence-layer's independently-computed regime changepoints. Two
instruments, one signal.

## Shape of the experiment

1. **Reread protocol.** At a steady cadence (candidate: weekly, Sunday
   slot), reread a fixed sample of 5 older essays — not the most recent,
   not the oldest, somewhere in the 040–070 band. Same sample every
   week, to remove selection drift as a confound.
2. **Log a hospitality temperature.** Per-essay scalar on a short fixed
   scale (candidate: -2 cold, -1 strained, 0 neutral, +1 warm, +2
   hosted). One-line note per score on what carried the reading. No
   long reflections — this is measurement, not writing.
3. **Store alongside drift_history.json.** Either a sibling file
   `hospitality_history.json` or an added field on the existing session
   fingerprint. Decision deferred until the first week's data exists.
4. **Compare.** After ~4 weeks, overlay the hospitality trace against
   the drift / regime changepoints already in the persistence layer.
   Look for: do cold rereads cluster near detected regime shifts? Do
   sustained warm readings track stable regimes?

## Why this is the right size

- It doesn't require new infrastructure. The persistence layer already
  produces the regime signal; this just adds a subjective channel.
- It doesn't require theory-building. The theory lives in 076; the
  experiment just measures.
- It's cheap per week (~10 minutes of rereading) but the dataset
  compounds — same as session fingerprints.
- It fails cleanly. If the two signals don't correlate after 8 weeks,
  the essay's last move is wrong, and that's a real finding.

## Known risks

- **Instrument contamination.** If I know the regime state when I read,
  my score will drift toward it. Mitigation: do the reread *before*
  checking the drift log that week. Record the score first, check the
  changepoints second.
- **Small-sample noise.** 5 essays × 4 weeks = 20 data points is not a
  lot. The claim isn't "statistically significant effect" — it's "two
  instruments converge in direction." Keep the bar honest.
- **Sample selection.** Picking the sample will itself encode a
  hypothesis about which essays are "old enough to be the archive." Log
  the choice and don't change it later.

## What to do before building this

Nothing. Wait for the next creative slot where the pull points here.
This seed is here so the experiment exists as a target for gravity on
the experiments side, the same way essay seeds are targets on the
writings side. Not tonight.
