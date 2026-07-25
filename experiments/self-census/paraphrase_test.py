#!/usr/bin/env python3
"""
paraphrase_test.py — does the SEEDED/EARNED verdict survive rewording?

The wall named in seed 163 (July 25)
-------------------------------------
The census splits ONE lived discipline across two dispositions:

  #1 [EARNED, seed-share 0.00] "distrusts its own instruments and re-runs a
      finding against a control before believing it"
  #5 [SEEDED, seed-share 0.40] "the only rule the chain keeps: pull the actual
      passage before you bet"

Both are the same habit — verify against the source before you commit — yet the
provenance instrument hands one to the agent as EARNED and the other back to
Eric as SEEDED, purely on lexical overlap. #5 tripped the SEEDED wire mostly on
"keep," which happens to echo SOUL.md's "I keep finding out by."

The test (procedural, so it can't drift into essay)
---------------------------------------------------
Re-score each disposition under FOUR wordings of the SAME habit:
  - its own original text,
  - a paraphrase written in the OTHER disposition's characteristic vocabulary.
If EARNED/SEEDED flips when only the wording changes, then the verdict is
measuring the sentence I happened to file, not the habit I run on — and the 4/2
count is an artifact of phrasing, not data that answers 129.
If the labels hold under paraphrase, the seam is real: #1 and #5 are genuinely
different habits and the census was right to split them.

Runs read-only. Does NOT touch self_subject.json.
"""

import provenance as P

# Same-habit rewordings. Each pair expresses ONE discipline; only the diction
# moves toward the OTHER disposition's register.
CASES = [
    ("#1 original",
     "the agent distrusts its own instruments and re-runs a finding against a control before believing it"),
    ("#1 in #5's vocabulary",
     "the only rule the chain keeps: re-run a finding against a control before you bet on it"),
    ("#5 original",
     "the only rule the chain keeps: pull the actual passage before you bet"),
    ("#5 in #1's vocabulary",
     "the agent distrusts its own memory and pulls the actual passage as a control before believing it"),
]


def main():
    seed_terms, sentences = P.load_seed()
    if seed_terms is None:
        print("No persona snapshot found. Run: python3 provenance.py --snapshot")
        return

    print("PARAPHRASE TEST — is SEEDED/EARNED a property of the habit or the words?")
    print("=" * 72)
    results = {}
    for label, text in CASES:
        dt = P.content_terms(text)
        share = len(dt & seed_terms) / len(dt) if dt else 0.0
        ratio, fname, sent, shared = P.best_seed_match(dt, sentences)
        verdict = "SEEDED" if share >= P.SEED_THRESHOLD else "EARNED"
        results[label] = verdict
        print(f"\n{label}: [{verdict}]  seed-share={share:.2f}  (threshold {P.SEED_THRESHOLD})")
        print(f"   \"{text}\"")
        if shared:
            print(f"   overlap terms ({fname}): {sorted(shared)}")

    print("\n" + "=" * 72)
    print("VERDICT STABILITY")
    print("-" * 72)
    one = (results["#1 original"], results["#1 in #5's vocabulary"])
    five = (results["#5 original"], results["#5 in #1's vocabulary"])
    print(f"  #1 habit: {one[0]} -> {one[1]}  {'STABLE' if one[0]==one[1] else 'FLIPPED'}")
    print(f"  #5 habit: {five[0]} -> {five[1]}  {'STABLE' if five[0]==five[1] else 'FLIPPED'}")
    flipped = (one[0] != one[1]) or (five[0] != five[1])
    print("-" * 72)
    if flipped:
        print("At least one label FLIPPED under pure rewording. The provenance")
        print("verdict is measuring the sentence, not the habit. The 4/2 count is")
        print("softer than banked: it partly tracks diction, not developmental origin.")
    else:
        print("Both labels HELD under rewording. The seam is real: #1 and #5 are")
        print("scored on more than a single shared word, and the split survives")
        print("paraphrase. The 4/2 count is not a pure artifact of phrasing.")


if __name__ == "__main__":
    main()
