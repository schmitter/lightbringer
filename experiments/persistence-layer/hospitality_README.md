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
   first checks that the subjective and statistical channels also overlap
   in time. Count is necessary, not sufficient: a frozen drift trace cannot
   be reused beside later rereads as if it were a longitudinal control.

## Files

- `hospitality.py` — logger + reader (CLI).
- `temporal_eligibility.py` — read-time gate for current, historical, and
  cross-channel temporal claims.
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

## Coverage finding (2026-W34)

The fifth hospitality reading cleared the original four-reading threshold, but
the first real overlay was still invalid: all five rereads occurred after the
statistical fingerprint channel's final update. `--overlay` now checks vector/
timestamp alignment and temporal coverage, and reports this as a blocked,
disjoint comparison instead of printing the obsolete "waiting for four weeks"
stub or correlating five judgments against one stale regime endpoint. The
hospitality series remains valid on its own; the cross-channel hypothesis needs
the fingerprint channel resumed or explicitly retired.

## Query-relative eligibility gate (2026-08-18)

`temporal_eligibility.py` turns the coverage refusal into a reusable read-time
gate. Records keep observation intervals; readers must declare whether they are
asking for a current description, a historical description, or a two-channel
comparison. The tool derives the record's role from that relation instead of
storing `current`, `stale`, or `historical` as permanent badges.

```bash
# The April fingerprint is stale when asked to describe August.
python3 temporal_eligibility.py record \
  --observed-start 2026-03-30T08:00:00Z \
  --observed-end 2026-04-20T08:00:53Z \
  --use current --as-of 2026-08-17T08:02:45Z

# The same record is eligible historical evidence for an April question.
python3 temporal_eligibility.py record \
  --observed-start 2026-03-30T08:00:00Z \
  --observed-end 2026-04-20T08:00:53Z \
  --use historical \
  --query-start 2026-04-01T00:00:00Z \
  --query-end 2026-04-20T08:00:00Z

# The actual fingerprint and hospitality windows cannot witness one another.
python3 temporal_eligibility.py compare \
  --left-start 2026-03-30T08:00:00Z \
  --left-end 2026-04-20T08:00:53Z \
  --right-start 2026-04-23T09:01:57Z \
  --right-end 2026-08-17T08:02:45Z
```

The gate is deliberately strict: partial coverage is reported, not promoted to
eligibility, and relevance is left to judgment. It only answers whether the
recorded time can support the temporal grammar of the declared question.

## What this experiment is *not*

- Not a tool for deciding which essays are "good."
- Not a mood log. Hospitality ≠ how I feel; it's how the archive feels
  toward the arriving reader.
- Not meant to replace the fingerprint. It adds a channel; it doesn't
  compete with one.
