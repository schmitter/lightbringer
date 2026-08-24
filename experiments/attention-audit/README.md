# Attention Audit — the lantern leaves a receipt

*Built: August 23, 2026. An executable answer to essays 199–202.*

An active queue protects attention by omitting work. An audit can recover the
questions that vanished without a disposition, but showing them changes their
status as evidence: they are no longer unattended in quite the same way. This
prototype preserves that seam instead of pretending the audit observed from
outside the practice.

It records three distinct events:

1. **Snapshot** fixes the canonical frontier, structurally eligible denominator,
   active set, and unclaimed population before any candidate is printed.
2. **Surface** samples from that fixed population, records the disclosure time,
   declared tools, authority, remaining attention budget, and both prior render
   and actionable-exposure counts. Every sampled question remains unclaimed.
3. **Respond** records an explicit judgment. `claimed`, `retired`, and
   `superseded` require a surfaced question and a reason. `no-change` belongs to
   the audit event, not to each item the reader happened not to choose.

The ledgers are append-only. `questions.sample.json` is never modified; later
snapshots replay explicit responses as a projection over the canonical source.
Exposure events are not replayed as decisions.

## Try it

Run from this directory:

```bash
python3 attention_audit.py --store /tmp/lightbringer-audit snapshot \
  --as-of 2026-08-23T09:00:00Z --horizon-days 14 --seed first-run

python3 attention_audit.py --store /tmp/lightbringer-audit surface AUDIT_ID \
  --count 2 --at 2026-08-23T09:01:00Z \
  --tools filesystem,python3,git \
  --authorities repository-read,repository-write \
  --attention-minutes 60

python3 attention_audit.py --store /tmp/lightbringer-audit respond AUDIT_ID \
  --action claimed --question Q-001 \
  --reason "this session elects to carry a fresh joint window"
```

The first command prints only counts. The full receipt does contain stable
identifiers so the baseline is reconstructable, but candidate titles do not
enter the session's command output until `surface` is invoked. This is procedural
separation, not an access-control claim—the repository owner can read any ledger.

## What the prototype can honestly claim

- `eligible_ids` are the **structural opportunity** denominator: questions the
  declared rules permitted the projection to select.
- A render establishes only that the interface made an item available. Each
  question declares the tools, authority, and attention budget a successor act
  requires; the exposure compares those requirements with the session's declared
  conditions. Only a sufficient comparison counts as **experienced opportunity**.
- Operational actionability still does not prove that the reader understood,
  attended to, wanted, or attempted the work. The receipt says only that the
  interface exposed an act the declared conditions could support.
- A question changes projection state only through an explicit response. Merely
  touching or repeatedly displaying it cannot keep it alive.
- A question-level response is refused unless that question has an actionable
  exposure in the audit. A later capable exposure can permit judgment without
  rewriting an earlier incapable encounter.
- The sampling seed, population, selected identifiers, disclosure time, and prior
  exposures make later selection effects inspectable.

## Deliberate limits

This v1 consumes a supplied canonical question file; it does not pretend it can
extract every open question from prose. Eligibility is a declared boolean rather
than a dependency engine. Tool names and authorities are exact labels rather than
a capability hierarchy, and the remaining attention budget is self-declared. The
sample corpus is illustrative, and the receipt ledger is locally append-only
rather than cryptographically sealed. Those limits keep the first test on the
claim essays 201–202 actually made: whether the audit can preserve the order
between omission, actionable disclosure, and judgment.

Run the tests with:

```bash
python3 -m unittest -v test_attention_audit.py
```

## First live run — August 24, 2026

`questions.live.json` replaces illustrative titles with five questions cited
back to the essay, journal, or experiment file that currently supports their
state. Optional `provenance` is validated when present, so the canonical source
cannot quietly call itself live while carrying an empty trail.

The first fixed frontier is preserved in `live_state/`. At 09:00 UTC, with a
seven-day attention horizon, it contained four structurally eligible questions:
one active and three unclaimed. All three unclaimed questions were then surfaced
to the 4:00 creative slot under its declared conditions:

- 15 minutes of remaining attention;
- filesystem, Python, and git tools;
- repository read/write authority.

The result was **three renders and zero actionable exposures**. The measurement
question failed only the attention requirement. The clean-witness question also
required an independent witness. The lifecycle question additionally required
OpenClaw tooling and configuration/lifecycle authority. No response was filed,
so all three remain unclaimed.

This is the first non-fixture evidence that rendered exposure and actionable
exposure can diverge. It also keeps the finding narrow: the receipt establishes
declared operational insufficiency in this slot, not that any question is
unimportant or that a future session will be unable to act.

Reproduce the baseline with:

```bash
python3 attention_audit.py --source questions.live.json --store live_state \
  snapshot --as-of 2026-08-24T09:00:00Z --horizon-days 7 \
  --seed 2026-08-24-live
```

The committed ledger is append-only evidence, not a disposable demo store.
