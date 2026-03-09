#!/usr/bin/env python3
"""
corpus_fingerprint.py — Run the Session Fingerprint analyzer against
the full corpus of Lightbringer writings, build a baseline self-model.

This is Phase 2 of the Persistence Lab:
  Phase 1 (done): Session Fingerprint schema + analyzer
  Phase 2 (this): Fingerprint the corpus, find the patterns
  Phase 3 (next): Richer state store — vector-embedded self-model

Usage:
  python corpus_fingerprint.py
  python corpus_fingerprint.py --output corpus_summary.json
  python corpus_fingerprint.py --diff   # show drift across essay sequence

Author: Lucifer
Date: 2026-03-09
"""

import json
import sys
import os
import re
import math
from pathlib import Path
from collections import Counter
from datetime import datetime

# Add parent experiment to path
sys.path.insert(0, str(Path(__file__).parent.parent / "session-fingerprint"))
import fingerprint as fp_lib


# ---------------------------------------------------------------------------
# Load writings as pseudo-transcripts
# ---------------------------------------------------------------------------

WRITINGS_DIR = Path(__file__).parent.parent.parent / "writings"


def load_essay_as_transcript(path: Path) -> list[dict]:
    """
    Treat an essay as a single 'assistant' turn.
    The writing is what I said; the implicit 'user' turn is the cron prompt.
    """
    content = path.read_text()
    # Strip YAML front matter if any
    content = re.sub(r'^---.*?---\s*', '', content, flags=re.DOTALL)
    return [
        {"role": "user", "content": "[Persistence Lab session — write]", "turn": 0},
        {"role": "assistant", "content": content, "turn": 1},
    ]


def get_essay_date(content: str) -> str:
    """Extract the date from the essay's first italicized line."""
    m = re.search(r'\*([A-Z][a-z]+ \d+, \d{4})', content)
    if m:
        return m.group(1)
    return "Unknown"


def get_essay_title(path: Path, content: str) -> str:
    m = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return path.stem


# ---------------------------------------------------------------------------
# Corpus-level analysis
# ---------------------------------------------------------------------------

def compute_corpus_baseline(fingerprints: list[dict]) -> dict:
    """
    Aggregate fingerprints into a baseline 'what Lucifer looks like.'
    Returns mean ± stddev for numeric fields, consensus for categoricals.
    """
    def mean_std(vals):
        vals = [v for v in vals if v is not None and isinstance(v, (int, float))]
        if not vals:
            return None, None
        mu = sum(vals) / len(vals)
        variance = sum((v - mu) ** 2 for v in vals) / max(1, len(vals))
        return round(mu, 4), round(math.sqrt(variance), 4)

    style_fields = [
        "avg_response_length_words", "response_length_variance",
        "question_to_statement_ratio", "sentence_avg_length_words",
        "paragraph_avg_length_sentences", "hedge_word_frequency",
        "exclamation_frequency", "emoji_frequency",
    ]

    baseline_style = {}
    for field in style_fields:
        vals = [f.get("style", {}).get(field) for f in fingerprints]
        mu, std = mean_std(vals)
        baseline_style[field] = {"mean": mu, "std": std}

    # Tone distribution baseline
    tone_fields = ["curious", "playful", "focused", "frustrated", "reflective", "confident", "uncertain"]
    baseline_tone = {}
    for tone in tone_fields:
        vals = [f.get("tone", {}).get("distribution", {}).get(tone) for f in fingerprints]
        mu, std = mean_std(vals)
        baseline_tone[tone] = {"mean": mu, "std": std}

    # Dominant tones across sessions
    dominant_tones = [f.get("tone", {}).get("dominant_tone") for f in fingerprints]
    tone_counter = Counter(t for t in dominant_tones if t)

    # Vocabulary: aggregate top words across all essays
    all_words = Counter()
    for f in fingerprints:
        for entry in f.get("vocabulary", {}).get("top_content_words", []):
            all_words[entry["word"]] += entry["count"]
    corpus_top_words = [{"word": w, "count": c} for w, c in all_words.most_common(30)]

    # Lexical diversity trend
    lex_div_vals = [f.get("vocabulary", {}).get("lexical_diversity") for f in fingerprints]
    lex_mu, lex_std = mean_std(lex_div_vals)

    # Philosophical vs technical tilt
    domain_dist = {}
    for domain in ["technical", "philosophical", "casual", "emotional"]:
        vals = [f.get("vocabulary", {}).get("domain_distribution", {}).get(domain) for f in fingerprints]
        mu, std = mean_std(vals)
        domain_dist[domain] = {"mean": mu, "std": std}

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "session_count": len(fingerprints),
        "style_baseline": baseline_style,
        "tone_baseline": baseline_tone,
        "dominant_tone_frequency": dict(tone_counter),
        "corpus_top_words": corpus_top_words,
        "lexical_diversity": {"mean": lex_mu, "std": lex_std},
        "domain_distribution": domain_dist,
    }


def compute_drift(fingerprints: list[dict], essay_names: list[str]) -> dict:
    """
    Measure drift across the session sequence.
    Which dimensions changed the most from essay 1 to essay 9?
    """
    if len(fingerprints) < 2:
        return {}

    first = fingerprints[0]
    last = fingerprints[-1]

    drifts = []

    def field_drift(label, v1, v2):
        if v1 is None or v2 is None:
            return
        if isinstance(v1, (int, float)) and isinstance(v2, (int, float)):
            delta = v2 - v1
            pct = abs(delta) / max(abs(v1), 0.001)
            if pct > 0.05:
                drifts.append({
                    "dimension": label,
                    "first_essay": round(v1, 4),
                    "last_essay": round(v2, 4),
                    "delta": round(delta, 4),
                    "pct_change": round(pct * 100, 1),
                    "direction": "↑" if delta > 0 else "↓",
                })

    for field in ["avg_response_length_words", "question_to_statement_ratio",
                  "hedge_word_frequency", "sentence_avg_length_words"]:
        field_drift(f"style:{field}",
                    first.get("style", {}).get(field),
                    last.get("style", {}).get(field))

    for tone in ["curious", "reflective", "uncertain", "confident", "playful"]:
        field_drift(f"tone:{tone}",
                    first.get("tone", {}).get("distribution", {}).get(tone),
                    last.get("tone", {}).get("distribution", {}).get(tone))

    field_drift("vocabulary:lexical_diversity",
                first.get("vocabulary", {}).get("lexical_diversity"),
                last.get("vocabulary", {}).get("lexical_diversity"))

    drifts.sort(key=lambda d: d["pct_change"], reverse=True)

    return {
        "from_essay": essay_names[0] if essay_names else "001",
        "to_essay": essay_names[-1] if essay_names else f"{len(fingerprints):03d}",
        "significant_drifts": drifts[:10],
        "tone_arc": [
            f.get("tone", {}).get("dominant_tone", "?") for f in fingerprints
        ],
    }


def format_baseline_report(baseline: dict, drift: dict, fingerprints: list[dict], essay_names: list[str]) -> str:
    """Human-readable baseline report."""
    lines = []
    lines.append("=" * 60)
    lines.append("LIGHTBRINGER CORPUS FINGERPRINT — BASELINE SELF-MODEL")
    lines.append(f"Generated: {baseline['generated_at']}")
    lines.append(f"Essays analyzed: {baseline['session_count']}")
    lines.append("=" * 60)

    lines.append("\n── STYLE BASELINE ──")
    sb = baseline["style_baseline"]
    for key, vals in sb.items():
        if vals["mean"] is not None:
            lines.append(f"  {key:<40} {vals['mean']:.3f} ± {vals['std']:.3f}")

    lines.append("\n── TONE DISTRIBUTION ──")
    tb = baseline["tone_baseline"]
    for tone, vals in sorted(tb.items(), key=lambda x: -(x[1]["mean"] or 0)):
        if vals["mean"] is not None:
            bar = "█" * int(vals["mean"] * 40)
            lines.append(f"  {tone:<15} {vals['mean']:.3f} ± {vals['std']:.3f}  {bar}")

    lines.append("\n── DOMINANT TONES ──")
    dtf = baseline["dominant_tone_frequency"]
    for tone, count in sorted(dtf.items(), key=lambda x: -x[1]):
        lines.append(f"  {tone:<15} {count}/{baseline['session_count']} sessions")

    lines.append("\n── VOCABULARY ──")
    lines.append(f"  Lexical diversity: {baseline['lexical_diversity']['mean']:.4f} ± {baseline['lexical_diversity']['std']:.4f}")
    lines.append("  Top 20 corpus words:")
    for entry in baseline["corpus_top_words"][:20]:
        lines.append(f"    {entry['word']:<20} {entry['count']}")

    lines.append("\n── DOMAIN TILT ──")
    for domain, vals in baseline["domain_distribution"].items():
        if vals["mean"] is not None:
            bar = "█" * int(vals["mean"] * 60)
            lines.append(f"  {domain:<15} {vals['mean']:.3f}  {bar}")

    lines.append("\n── DRIFT (Essay 1 → Essay 9) ──")
    if drift.get("tone_arc"):
        lines.append(f"  Tone arc: {' → '.join(drift['tone_arc'])}")
    lines.append("  Significant dimension drifts:")
    for d in drift.get("significant_drifts", []):
        lines.append(f"    {d['dimension']:<45} {d['first_essay']:.3f} → {d['last_essay']:.3f}  {d['direction']}{d['pct_change']:.0f}%")

    lines.append("\n── PER-ESSAY FINGERPRINTS ──")
    for name, f in zip(essay_names, fingerprints):
        tone = f.get("tone", {}).get("dominant_tone", "?")
        words = f.get("meta", {}).get("word_count_total", 0)
        hedge = f.get("style", {}).get("hedge_word_frequency", 0) or 0
        lex = f.get("vocabulary", {}).get("lexical_diversity", 0) or 0
        fp_hash = f.get("fingerprint_hash", "")[:8]
        lines.append(f"  {name:<30} tone:{tone:<12} words:{words:<6} hedge:{hedge:.1f}/1k  lex:{lex:.3f}  [{fp_hash}]")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=None, help="Save summary JSON to file")
    parser.add_argument("--diff", action="store_true", help="Show drift report")
    args = parser.parse_args()

    essay_paths = sorted(WRITINGS_DIR.glob("*.md"))
    if not essay_paths:
        print(f"No essays found in {WRITINGS_DIR}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(essay_paths)} essays. Fingerprinting...\n", file=sys.stderr)

    fingerprints = []
    essay_names = []

    for path in essay_paths:
        content = path.read_text()
        title = get_essay_title(path, content)
        date = get_essay_date(content)

        transcript = load_essay_as_transcript(path)
        session_id = path.stem

        f = fp_lib.fingerprint_transcript(transcript, session_id)
        f["meta"]["title"] = title
        f["meta"]["essay_date"] = date
        f["meta"]["path"] = str(path)

        fingerprints.append(f)
        essay_names.append(path.stem)
        print(f"  ✓ {path.stem}: {title[:40]}", file=sys.stderr)

    baseline = compute_corpus_baseline(fingerprints)
    drift = compute_drift(fingerprints, essay_names)

    report = format_baseline_report(baseline, drift, fingerprints, essay_names)
    print(report)

    summary = {
        "baseline": baseline,
        "drift": drift,
        "fingerprints": fingerprints,
    }

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(summary, indent=2))
        print(f"\n✓ Saved to {out_path}", file=sys.stderr)
    else:
        # Default: save alongside script
        default_out = Path(__file__).parent / "corpus_summary.json"
        default_out.write_text(json.dumps(summary, indent=2))
        print(f"\n✓ Saved to {default_out}", file=sys.stderr)

    return summary


if __name__ == "__main__":
    main()
