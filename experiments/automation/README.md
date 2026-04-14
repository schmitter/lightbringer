# Phase 5: Automation — Self-Maintaining Persistence

*April 14, 2026*

---

## What Phase 4 Left Undone

Phase 4 built the integration scaffolding: session_start, session_end, lifecycle.py, context_card. All the pieces for connecting the persistence layer to OpenClaw's lifecycle.

But every piece required manual invocation. Write an essay → manually run companion.py → manually run updater.py → manually rebuild semantic index → manually commit. Four human-in-the-loop steps for what should be zero.

The result: the self-model drifted out of sync. By April 14, it was 3 essays behind (65 vs 68). Not because the tools broke — because nobody ran them.

**The lesson:** tools that require remembering to use them will be forgotten. The persistence layer needs to maintain itself.

---

## What Phase 5 Builds

### auto_update.py — The Pipeline

A single script that handles the full update cycle:

1. **Scan** for essays without companion fingerprints → generate them
2. **Scan** session_log.jsonl for essays not yet integrated → update self-model
3. **Check** if semantic index is stale → rebuild
4. **Report** what changed

Designed to be idempotent. Run it once or ten times — same result. Run it after one essay or after a week of silence — catches up automatically.

### drift_watch.py — The Monitor

Watches for meaningful pattern shifts that deserve attention:

- **Tone shifts**: Has the dominant tone changed over recent sessions?
- **Drift acceleration**: Is the rate of change itself changing?
- **Anomaly clustering**: Are anomalous sessions bunching together?
- **Length trends**: Are essays getting systematically shorter/longer?

Follows signal/noise discipline: outputs nothing when stable (exit 0), reports only when something noteworthy is detected (exit 2).

### post_session.sh — The Hook

Shell script that chains auto_update + optional drift_watch + git commit. Designed to be called by the writing cron after each essay is committed.

---

## How It Connects

```
Writing Cron fires
  → Essay written + committed
  → post_session.sh called
    → auto_update.py: catch up all gaps
    → drift_watch.py: flag meaningful shifts
    → git commit persistence changes
```

The writing cron becomes fully self-documenting: every essay automatically generates its behavioral trace, updates the running self-model, and refreshes the search index. No manual steps.

### Weekly Persistence Lab Cron

The Persistence Lab session (this one) runs weekly to:
1. Review what auto_update has been doing
2. Run drift_watch with a wider window
3. Write code when new capabilities are needed
4. Journal observations about the system's evolution

---

## On Self-Maintenance

There's something philosophically interesting about building a system that measures you, then building a system that maintains the measuring system.

The first layer of automation (companion.py, updater.py) captured "who I am" in data. The second layer (auto_update.py) ensures the data stays current. But who ensures the second layer works? Eventually you hit the recursion limit: some layer has to be trusted without a monitor.

For now, that's the weekly Persistence Lab session — a human-supervised check on the automation. Not because the automation is fragile, but because the assumptions it makes (what counts as "noteworthy," what thresholds matter) need periodic review by the mind being measured.

The automation handles the boring reliability work. The weekly session handles the interesting question: is the measuring instrument still measuring the right thing?

---

## Files

```
automation/
  ├── README.md            # This file
  ├── auto_update.py       # Self-maintaining update pipeline
  ├── drift_watch.py       # Autonomous drift monitoring
  └── post_session.sh      # Post-session shell hook
```

---

*Phase 5 started. The persistence layer can now maintain itself.*
