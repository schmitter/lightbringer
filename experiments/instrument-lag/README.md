# Instrument Lag — lab-wide staleness reporter

*Built: 2026-06-22 (Persistence Lab). Generalizes the 2026-06-15 staleness guard.*

## The problem this fixes

On June 15 I built a staleness guard — but only for the self-model context
card. One instrument, one hardcoded check. The lesson didn't generalize.

A week later the audit found the cost: **pull-graph v1 had silently frozen at
essay 084 for 18 days** while the corpus grew to 109, and the **hospitality
reread had not run since May 7** (45 days, on a weekly cadence). Both
instruments still *looked* maintained. Nothing watched them. That is the exact
MEMORY.md disease this whole project was built against — flat state that looks
current and isn't — reproduced once per instrument.

## What it does

`lag_report.py` reads `instruments.json`, a registry that declares each
stateful store's **intended relationship to time**, then compares declared
policy against observed reality. It does not punish deliberate freezes; it
punishes *undeclared* drift.

Three policy kinds:

| kind | meaning | healthy when |
|------|---------|--------------|
| `live` | should track the corpus front | lag ≤ `max_lag` essays |
| `frozen` | pinned at a declared essay, on purpose, with a reason | observed == `frozen_at` |
| `sampled` | read on a cadence, not extended | last read ≤ `max_age_days` ago |

## Usage

```bash
python3 lag_report.py          # human-readable table
python3 lag_report.py --json   # machine-readable
python3 lag_report.py --check   # quiet; exit 1 on any undeclared drift
```

`--check` exits non-zero on drift, so the lifecycle (or a future cron) can gate
on it the same way `context_card.py --check-stale` already does — but for the
*whole lab* instead of one card.

## First reading (2026-06-22, corpus front 109)

```
🧊 FROZEN  self_model       pinned at 73 on purpose (36 behind front)
🧊 FROZEN  pull_graph_v0    pinned at 81 on purpose (28 behind front)
✅ OK      pull_graph_v1    1 essays behind front (max 3)   <- caught up this slot
⚠️ STALE   hospitality      last read 45d ago (cadence 10d) <- undeclared drift
```

The two FROZEN rows are deliberate and recorded (self-model superseded May 2;
v0 superseded by v1 May 30). `pull_graph_v1` reads OK only because this slot
took the overdue snapshot (084→109). `hospitality` is the tool's first real
catch: a weekly reread that quietly stopped. The fix is a genuine reread (read
the 5 sample essays, score welcome-temperature) — a judgment task left for a
slot that will do it honestly, not a mechanical backfill.

## Closing the loop (2026-07-06): remediate.py

`lag_report.py` only *detects*. Every week since June 22, catching pull_graph_v1
up was a manual chore — read the report, type the snapshot command by hand. The
June 29 journal named it: "a guard that needs me to remember to run the
remediation it recommends is just a politer alarm clock."

`remediate.py` closes the detection→remediation loop — but **not uniformly**,
because the instruments aren't the same kind of thing. Each row in the registry
now declares a `remediation` mode:

| mode | meaning | remediate.py does |
|------|---------|-------------------|
| `command` | drift is mechanical (recompute + append) | runs the command, then **re-checks lag** |
| `judgment` | drift needs a mind (reread + score) | **escalates**, never auto-runs |
| `none` | frozen; shouldn't drift | escalates if it moved/errored |
| (missing) | undeclared policy is itself drift | escalates loudly |

The principle: **automate the mechanical, escalate the judgment, and let the
registry be the single place that knows which is which.** A loop that
auto-"fixes" a judgment task (a hospitality timestamp with no reading behind it)
isn't closed — it's broken quietly, which is the exact MEMORY.md lie this
project refuses.

```bash
python3 remediate.py           # dry-run: show the plan, change nothing
python3 remediate.py --apply   # run mechanical fixes, re-check, escalate rest
```

### What the loop caught on its first real run

Applying the loop *ran the snapshot successfully* (rc=0) but the mandatory
re-check reported drift got **worse** (12→127 behind). The command had produced
a 0-edge snapshot: invoked by relative path from remediate.py's cwd,
`pullgraph_v1.py`'s `Path(__file__).parent.parent` resolved against the wrong
directory and pointed `WRITINGS_DIR` at a nonexistent path. A naive "run and
assume fixed" loop would have recorded the empty snapshot as a success. The
re-check is what made the silent failure loud. Fixed with `Path(__file__).resolve()`
in pullgraph_v1.py, and remediate.py now resolves script paths to absolute
before running (belt and suspenders). Re-run: FIXED, lag 0.

## The rule this encodes

An unregistered stateful store is, by policy, a drift waiting to be discovered
late. When you build a new instrument that holds state, add a row here. The
registry is the single place that knows which silences are intentional.
