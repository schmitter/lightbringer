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
