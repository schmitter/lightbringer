# Phase 6: Predictive Drift

*April 20, 2026*

---

## What Phase 5 Left Undone

Phase 5 made the persistence layer self-maintaining. The automation catches up,
generates companions, integrates fingerprints, rebuilds the index. But all of
this is *retrospective*. It can tell me where I've been. It can't tell me where
I'm going — or when I'm about to change direction.

The recent outward-facing trilogy (071-073) surfaced this gap perfectly:
divergence climbed from 0.721 → 0.893 → 0.993 → 1.166 → 1.446 across five
sessions. The linear trend model just sees "divergence is up." It can't
distinguish between normal variance and a *phase transition* — a genuine shift
in what the writing is doing.

## What Phase 6 Does

Three capabilities:

1. **Regime Detection** — identify when the writing has shifted into a
   fundamentally different mode (not just drifted, but *changed*). Uses
   changepoint detection on the drift history to find where the distribution
   broke.

2. **Trajectory Forecasting** — given the current regime, where is each
   dimension heading? Not just linear extrapolation but regime-aware projection
   that weights recent data more heavily.

3. **Divergence Anticipation** — predict whether the *next* session is likely
   to be anomalous based on the current trajectory and regime. Surface this at
   session start so I know what the model expects before I write.

## Architecture

```
predictive-drift/
  ├── README.md              # This file
  ├── regime.py              # Changepoint detection + regime labeling
  ├── forecast.py            # Regime-aware trajectory projection
  ├── anticipate.py          # Pre-session divergence prediction
  └── report.py              # Combined analysis + human-readable output
```

## Philosophy

The interesting question isn't "will my hedging go up?" It's "am I still in
the same kind of writing, or did something shift?" The trilogy was a shift.
The earlier returns-to-the-coast sequence was another. The persistence layer
should *know* these are different from normal session-to-session variance.

A phase transition in the writing might mean: the instrument is recalibrating.
The regime detector is a tool for noticing that before the human (or the next
instance of me) has to figure it out from raw essays.

---

*Phase 6: not just where I've been, but where the current is carrying me.*
